import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail

from syllabi.models import Syllabus
from .models import SyllabusAuditLog, SyllabusStatusLog

logger = logging.getLogger(__name__)

def _status_label(status: str) -> str:
    """Получает человекочитаемое название статуса."""
    try:
        return Syllabus.Status(status).label
    except Exception:
        return status

def _collect_role_emails(role_name: str) -> list[str]:
    """Собирает email-адреса пользователей по роли или группе."""
    User = get_user_model()
    # Ищем пользователей, у которых role совпадает ИЛИ которые в группе с таким названием
    qs = User.objects.filter(is_active=True).exclude(email="")
    
    # Поиск по полю role (если оно есть в модели)
    if hasattr(User, 'role'):
        qs_role = qs.filter(role=role_name)
    else:
        qs_role = qs.none()

    # Поиск по группам (стандарт Django)
    qs_group = qs.filter(groups__name__icontains=role_name)

    # Объединяем результаты
    final_qs = (qs_role | qs_group).distinct()
    return list(final_qs.values_list("email", flat=True))


def _safe_send_mail(subject: str, message: str, recipients: list[str]) -> None:
    """Безопасная отправка почты."""
    if not recipients:
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@almausyllabus.kz")
    try:
        send_mail(subject, message, from_email, recipients, fail_silently=False)
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def change_status(user, syllabus: Syllabus, new_status: str, comment: str = ""):
    """
    Главная функция управления переходами статусов.
    """
    old_status = syllabus.status
    comment = (comment or "").strip()

    # --- 1. ОПРЕДЕЛЕНИЕ ПРАВ ---
    # Пользователь считается админом, если он superuser или staff
    is_admin = user.is_superuser or user.is_staff
    
    # Получаем список групп пользователя
    user_groups = list(user.groups.values_list('name', flat=True))
    user_role = getattr(user, 'role', '')

    # Проверка на Декана: Админ ИЛИ роль 'dean' ИЛИ группа 'Deans'
    is_dean = is_admin or (user_role == 'dean') or ('Deans' in user_groups)
    
    # Проверка на УМУ: Админ ИЛИ роль 'umu' ИЛИ группа 'UMU'
    is_umu = is_admin or (user_role == 'umu') or ('UMU' in user_groups)
    
    is_creator = (user == syllabus.creator)

    if new_status == old_status:
        return syllabus

    # --- 2. ЛОГИКА ПЕРЕХОДОВ ---

    # А) ОТПРАВКА ДЕКАНУ (Преподаватель -> Декан)
    if new_status == Syllabus.Status.REVIEW_DEAN:
        # Отправлять может автор или админ
        if not (is_creator or is_admin):
            raise PermissionDenied("Только автор может отправить силлабус на проверку.")
        
        # Разрешаем отправку из статусов: Черновик, Доработка, Проверка ИИ
        allowed_prev = [Syllabus.Status.DRAFT, Syllabus.Status.CORRECTION, Syllabus.Status.AI_CHECK]
        if old_status not in allowed_prev and not is_admin:
             # Если статус уже REVIEW_DEAN, ничего страшного, пропускаем
             if old_status != Syllabus.Status.REVIEW_DEAN:
                raise PermissionDenied("Неверный порядок статусов.")

    # Б) СОГЛАСОВАНИЕ ДЕКАНА -> ПЕРЕДАЧА В УМУ
    elif new_status == Syllabus.Status.REVIEW_UMU:
        if not is_dean:
            raise PermissionDenied("Только Декан может передать силлабус в УМУ.")
        
        # Проверка: должен быть на этапе "У Декана"
        if old_status != Syllabus.Status.REVIEW_DEAN and not is_admin:
            raise PermissionDenied("Силлабус должен находиться на проверке у Декана.")

    # В) ФИНАЛЬНОЕ УТВЕРЖДЕНИЕ (УМУ)
    elif new_status == Syllabus.Status.APPROVED:
        if not is_umu:
            raise PermissionDenied("Только сотрудник УМУ может утвердить силлабус.")
        
        if old_status != Syllabus.Status.REVIEW_UMU and not is_admin:
            raise PermissionDenied("Силлабус должен находиться на проверке в УМУ.")

    # Г) ВОЗВРАТ НА ДОРАБОТКУ
    elif new_status == Syllabus.Status.CORRECTION:
        if not (is_dean or is_umu):
            raise PermissionDenied("У вас нет прав возвращать силлабус.")
        
        if not comment:
            raise ValueError("Укажите причину возврата (комментарий обязателен).")
        
        # Записываем, кто вернул
        role_label = "Деканат" if is_dean else "УМУ"
        syllabus.ai_feedback = f"[{role_label}]: {comment}"

    else:
        # Если статус неизвестен
        raise ValueError(f"Неизвестный статус: {new_status}")

    # --- 3. СОХРАНЕНИЕ ---
    syllabus.status = new_status
    syllabus.save(update_fields=["status", "ai_feedback"])

    # --- 4. ЛОГИРОВАНИЕ ---
    try:
        SyllabusStatusLog.objects.create(
            syllabus=syllabus,
            from_status=old_status,
            to_status=new_status,
            changed_by=user,
            comment=comment,
        )

        SyllabusAuditLog.objects.create(
            syllabus=syllabus,
            actor=user,
            action=SyllabusAuditLog.Action.STATUS_CHANGED,
            metadata={"from": old_status, "to": new_status},
            message=f"Переход: {_status_label(old_status)} -> {_status_label(new_status)}"
        )
    except Exception:
        # Логи не должны ломать основной процесс
        pass

    # --- 5. УВЕДОМЛЕНИЯ (EMAIL) ---
    subject = ""
    message = ""
    recipients = []

    if new_status == Syllabus.Status.REVIEW_DEAN:
        recipients = _collect_role_emails("Deans")
        subject = f"📝 На проверку: {syllabus.course.code}"
        message = f"Силлабус {syllabus.course.code} отправлен на проверку Декану."

    elif new_status == Syllabus.Status.REVIEW_UMU:
        recipients = _collect_role_emails("UMU")
        subject = f"🛡️ Согласовано Деканом: {syllabus.course.code}"
        message = f"Декан согласовал силлабус {syllabus.course.code}. Ожидает проверки УМУ."

    elif new_status == Syllabus.Status.CORRECTION:
        if syllabus.creator.email:
            recipients = [syllabus.creator.email]
            subject = f"⚠️ Требуются правки: {syllabus.course.code}"
            message = f"Ваш силлабус возвращен на доработку.\nКомментарий: {comment}"

    elif new_status == Syllabus.Status.APPROVED:
        if syllabus.creator.email:
            recipients = [syllabus.creator.email]
            subject = f"✅ Утверждено: {syllabus.course.code}"
            message = f"Ваш силлабус {syllabus.course.code} полностью утвержден!"

    if recipients:
        _safe_send_mail(subject, message, recipients)

    return syllabus