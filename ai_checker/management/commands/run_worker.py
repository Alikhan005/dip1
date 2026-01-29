import time
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from syllabi.models import Syllabus
from ai_checker.services import run_ai_check

# Настраиваем логирование, чтобы видеть всё в консоли
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Запускает фоновый процесс проверки силлабусов через ИИ'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Воркер запущен! Ожидание задач...'))
        
        while True:
            # 1. Ищем силлабус со статусом "На проверке ИИ"
            # order_by('updated_at') берет самый старый из очереди (FIFO)
            syllabus = Syllabus.objects.filter(status=Syllabus.Status.AI_CHECK).order_by('updated_at').first()
            
            if syllabus:
                self.stdout.write(self.style.WARNING(f'Найден силлабус ID {syllabus.id}. Начинаю проверку...'))
                
                try:
                    # 2. Запускаем "умную" проверку (тот самый код из services.py)
                    # Эта функция занимает время (5-30 сек), но сайт не виснет
                    result_record = run_ai_check(syllabus)
                    
                    # 3. Анализируем результат
                    # В services.py мы сохраняем raw_result с ключом 'approved'
                    raw_data = result_record.raw_result or {}
                    is_approved = raw_data.get('approved', False)
                    feedback = raw_data.get('feedback', '')
                    
                    if is_approved:
                        # Если ИИ одобрил -> Отправляем Декану
                        syllabus.status = Syllabus.Status.REVIEW_DEAN
                        status_msg = "ОДОБРЕНО ИИ"
                        self.stdout.write(self.style.SUCCESS(f'Силлабус {syllabus.id}: Успех -> Декану'))
                    else:
                        # Если нашел ошибки -> Возвращаем преподавателю
                        syllabus.status = Syllabus.Status.CORRECTION
                        status_msg = "ОТКЛОНЕНО ИИ"
                        self.stdout.write(self.style.ERROR(f'Силлабус {syllabus.id}: Найдены ошибки -> На доработку'))
                    
                    # Сохраняем результат
                    syllabus.save()

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'Ошибка при обработке ID {syllabus.id}: {e}'))
                    # Чтобы не зациклиться на ошибке, можно временно перевести в статус коррекции
                    syllabus.status = Syllabus.Status.CORRECTION
                    syllabus.ai_feedback = f"Критическая ошибка проверки: {e}"
                    syllabus.save()
            
            else:
                # Если задач нет, спим 5 секунд, чтобы не грузить процессор
                time.sleep(5)