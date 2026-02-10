import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction

from syllabi.models import Syllabus
from .models import SyllabusAuditLog, SyllabusStatusLog

logger = logging.getLogger(__name__)
User = get_user_model()

def _status_label(status: str) -> str:
    """Получает человекочитаемое название статуса."""
    try:
        return Syllabus.Status(status).label
    except Exception:
        return status

def _collect_role_emails(role_key: str) -> list[str]:
    """
    Собирает email-адреса пользователей по их роли.
    role_key: 'dean' или 'umu'
    """
    # Ищем пользователей, у которых role == role_key
    qs = User.objects.filter(is_active=True, role=role_key).exclude(email="")
    emails = list(qs.values_list("email", flat=True))
    
    if not emails:
        logger.warning(f"Не найдены пользователи с ролью '{role_key}' для отправки уведомлений.")
    
    return emails

def _safe_send_mail(subject: str, message: str, recipients: list[str]) -> None:
    """Безопасная отправка почты (не роняет процесс при ошибке)."""
    if not recipients:
        return
        
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@almau.edu.kz")
    
    try:
        # Для локальной разработки письма будут падать в консоль (если настроен console backend)
        send_mail(
            subject=subject,
            message=message + "\n\n--\nСистема управления силлабусами AlmaU",
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=True
        )
        logger.info(f"📧 Письмо '{subject}' отправлено: {recipients}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки почты: {e}")


def change_status(user, syllabus: Syllabus, new_status: str, comment: str = ""):
    """
    Главная функция смены статуса.
    1. Проверяет права.
    2. Меняет статус.
    3. Пишет логи.
    4. Отправляет уведомления.
    """
    old_status = syllabus.status
    comment = (comment or "").strip()

    # --- 1. ОПРЕДЕЛЕНИЕ ПРАВ ---
    is_admin = user.is_superuser or user.is_staff
    user_role = getattr(user, 'role', '')
    
    is_dean = is_admin or (user_role == 'dean')
    is_umu = is_admin or (user_role == 'umu')
    is_creator = (user == syllabus.creator)

    if new_status == old_status:
        return syllabus

    # --- 2. ЛОГИКА ПЕРЕХОДОВ (Кто куда может перевести) ---

    # А) ОТПРАВКА ДЕКАНУ (Преподаватель -> Декан)
    if new_status == Syllabus.Status.REVIEW_DEAN:
        if not (is_creator or is_admin):
            raise PermissionDenied("Только автор может отправить силлабус.")
        # Разрешаем повторную отправку
        allowed_prev = [Syllabus.Status.DRAFT, Syllabus.Status.CORRECTION, Syllabus.Status.AI_CHECK, Syllabus.Status.REVIEW_DEAN]
        if old_status not in allowed_prev and not is_admin:
             raise PermissionDenied("Неверный статус для отправки Декану.")

    # Б) СОГЛАСОВАНИЕ ДЕКАНА -> ПЕРЕДАЧА В УМУ
    elif new_status == Syllabus.Status.REVIEW_UMU:
        if not is_dean:
            raise PermissionDenied("Только Декан может передать силлабус в УМУ.")
        if old_status != Syllabus.Status.REVIEW_DEAN and not is_admin:
            raise PermissionDenied("Силлабус должен быть на проверке у Декана.")

    # В) ФИНАЛЬНОЕ УТВЕРЖДЕНИЕ (УМУ)
    elif new_status == Syllabus.Status.APPROVED:
        if not is_umu:
            raise PermissionDenied("Только сотрудник УМУ может утвердить силлабус.")
        if old_status != Syllabus.Status.REVIEW_UMU and not is_admin:
            raise PermissionDenied("Силлабус должен быть на проверке в УМУ.")

    # Г) ВОЗВРАТ НА ДОРАБОТКУ
    elif new_status == Syllabus.Status.CORRECTION:
        if not (is_dean or is_umu):
            raise PermissionDenied("У вас нет прав возвращать силлабус.")
        if not comment:
            raise ValueError("Укажите причину возврата (комментарий обязателен).")
        
        # Сохраняем комментарий в поле ИИ, чтобы его было видно на странице
        role_label = "Деканат" if is_dean else "УМУ"
        syllabus.ai_feedback = f"<b>[{role_label} вернул на доработку]:</b><br>{comment}"

    else:
        # Для остальных статусов (например AI_CHECK) разрешаем смену без проверок ролей
        pass

    # --- 3. АТОМАРНОЕ СОХРАНЕНИЕ И ЛОГИ ---
    with transaction.atomic():
        syllabus.status = new_status
        syllabus.save(update_fields=["status", "ai_feedback"])

        # Лог переходов
        SyllabusStatusLog.objects.create(
            syllabus=syllabus,
            from_status=old_status,
            to_status=new_status,
            changed_by=user,
            comment=comment,
        )
        
        # Аудит лог
        SyllabusAuditLog.objects.create(
            syllabus=syllabus,
            actor=user,
            action=SyllabusAuditLog.Action.STATUS_CHANGED,
            metadata={"from": old_status, "to": new_status},
            message=f"Переход: {_status_label(old_status)} -> {_status_label(new_status)}"
        )

    # --- 4. ОТПРАВКА УВЕДОМЛЕНИЙ ---
    try:
        subject = ""
        message = ""
        recipients = []

        # Сценарий 1: Учитель отправил Декану -> Уведомляем Деканов
        if new_status == Syllabus.Status.REVIEW_DEAN:
            recipients = _collect_role_emails("dean")
            subject = f"📝 На проверку: {syllabus.course.code}"
            message = f"Поступил силлабус на проверку.\nКурс: {syllabus.course.display_title}\nАвтор: {syllabus.creator.get_full_name()}"

        # Сценарий 2: Декан согласовал -> Уведомляем УМУ
        elif new_status == Syllabus.Status.REVIEW_UMU:
            recipients = _collect_role_emails("umu")
            subject = f"🛡️ Согласовано Деканом: {syllabus.course.code}"
            message = f"Декан одобрил силлабус. Требуется финальная проверка УМУ.\nКурс: {syllabus.course.display_title}"

        # Сценарий 3: УМУ утвердило -> Уведомляем Учителя
        elif new_status == Syllabus.Status.APPROVED:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"✅ Утверждено: {syllabus.course.code}"
                message = f"Поздравляем! Ваш силлабус по курсу {syllabus.course.code} официально утвержден."

        # Сценарий 4: Вернули на доработку -> Уведомляем Учителя
        elif new_status == Syllabus.Status.CORRECTION:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"⚠️ Требуются правки: {syllabus.course.code}"
                message = f"Ваш силлабус возвращен на доработку.\n\nКомментарий проверяющего:\n{comment}"

        # Отправляем
        if recipients:
            _safe_send_mail(subject, message, recipients)

    except Exception as e:
        logger.error(f"Ошибка в блоке уведомлений: {e}")

    return syllabus