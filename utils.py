import os
import asyncio
import speech_recognition as sr
from pydub import AudioSegment
from config import TEMP_DIR, SPEECH_LANGUAGE
import re

class VoiceProcessor:
    def __init__(self):
        self.recognizer = sr.Recognizer()
    
    async def convert_ogg_to_wav(self, ogg_path: str) -> str:
        wav_path = ogg_path.replace('.ogg', '.wav')
        # Pydub использует FFmpeg, это блокирующая операция, выносим в тред
        await asyncio.to_thread(self._convert, ogg_path, wav_path)
        return wav_path

    def _convert(self, input_path, output_path):
        audio = AudioSegment.from_ogg(input_path)
        audio.export(output_path, format='wav')
    
    async def recognize_speech(self, wav_path: str) -> str:
        # Google API - синхронный запрос. Оборачиваем в to_thread
        return await asyncio.to_thread(self._recognize_sync, wav_path)

    def _recognize_sync(self, wav_path):
        try:
            with sr.AudioFile(wav_path) as source:
                audio_data = self.recognizer.record(source)
                return self.recognizer.recognize_google(audio_data, language=SPEECH_LANGUAGE)
        except sr.UnknownValueError:
            raise Exception("Речь не распознана")
        except sr.RequestError:
            raise Exception("Ошибка сервиса Google")

    async def process_voice(self, voice_file_path: str) -> str:
        ogg_path = None
        wav_path = None
        try:
            # Копируем файл в нужную структуру (если нужно) или используем как есть
            ogg_path = voice_file_path
            wav_path = await self.convert_ogg_to_wav(ogg_path)
            text = await self.recognize_speech(wav_path)
            return text
        finally:
            # Чистим
            for path in [ogg_path, wav_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except:
                        pass

# ==================== УТИЛИТЫ ДЛЯ ОПРЕДЕЛЕНИЯ НАМЕРЕНИЯ ====================

class IntentDetector:
    """Определение намерения пользователя из текста"""
    
    # Паттерны запросов рецептов
    RECIPE_REQUEST_PATTERNS = [
        r'дай\s+рецепт\s+(.+)',
        r'рецепт\s+(.+)',
        r'как\s+приготовить\s+(.+)',
        r'как\s+сделать\s+(.+)',
        r'хочу\s+приготовить\s+(.+)',
        r'хочу\s+сделать\s+(.+)',
        r'готовим\s+(.+)',
        r'приготовь\s+(.+)',
        r'сделай\s+(.+)',
        r'как\s+готовить\s+(.+)',
        r'как\s+приготовить\s+(.+)',
        r'recipe\s+for\s+(.+)',
        r'how\s+to\s+cook\s+(.+)',
        r'how\s+to\s+make\s+(.+)',
        r'i\s+want\s+to\s+cook\s+(.+)',
        r'i\s+want\s+to\s+make\s+(.+)',
        r'cook\s+(.+)',
        r'make\s+(.+)'
    ]
    
    # Паттерны списка продуктов
    PRODUCTS_PATTERNS = [
        r'^[а-яёa-z0-9\s,\-\.]+$',  # Простой список ингредиентов
        r'у\s+меня\s+есть\s+(.+)',
        r'имеется\s+(.+)',
        r'в\s+наличии\s+(.+)',
        r'продукты\s*:\s*(.+)',
        r'ингредиенты\s*:\s*(.+)',
        r'i\s+have\s+(.+)',
        r'products?\s*:\s*(.+)',
        r'ingredients?\s*:\s*(.+)'
    ]
    
    @staticmethod
    def is_recipe_request(text: str) -> bool:
        """Определяет, является ли текст запросом рецепта"""
        if not text or len(text.strip()) < 3:
            return False
        
        text_lower = text.lower().strip()
        
        # Быстрая проверка по началу строки
        if any(text_lower.startswith(phrase) for phrase in [
            'дай рецепт', 'рецепт', 'как приготовить', 'как сделать',
            'хочу приготовить', 'хочу сделать', 'приготовь', 'сделай'
        ]):
            return True
        
        # Более точная проверка по регулярным выражениям
        for pattern in IntentDetector.RECIPE_REQUEST_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    @staticmethod
    def extract_dish_name(text: str) -> str:
        """Извлекает название блюда из запроса"""
        if not text:
            return ""
        
        text_lower = text.lower().strip()
        
        # Убираем ключевые фразы
        phrases_to_remove = [
            'дай рецепт', 'рецепт', 'как приготовить', 'как сделать',
            'хочу приготовить', 'хочу сделать', 'приготовь', 'сделай',
            'как готовить', 'готовим', 'recipe for', 'how to cook',
            'how to make', 'i want to cook', 'i want to make',
            'cook', 'make', 'пожалуйста', 'please'
        ]
        
        # Убираем фразы с начала
        for phrase in phrases_to_remove:
            if text_lower.startswith(phrase):
                text_lower = text_lower[len(phrase):].strip()
        
        # Убираем знаки препинания в начале
        text_lower = re.sub(r'^[\s,:;\.\-!?]+', '', text_lower)
        
        # Убираем лишние пробелы
        text_lower = re.sub(r'\s+', ' ', text_lower).strip()
        
        # Капитализируем первое слово
        if text_lower:
            return text_lower[0].upper() + text_lower[1:]
        
        return ""
    
    @staticmethod
    def is_products_list(text: str) -> bool:
        """Определяет, является ли текст списком продуктов"""
        if not text or len(text.strip()) < 2:
            return False
        
        text_lower = text.lower().strip()
        
        # Быстрая проверка по паттернам продуктов
        for pattern in IntentDetector.PRODUCTS_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        
        # Эвристика: если содержит много запятых или "и" - вероятно, продукты
        comma_count = text_lower.count(',')
        and_count = text_lower.count(' и ')
        
        if comma_count >= 2 or (comma_count >= 1 and and_count >= 1):
            return True
        
        # Эвристика: если текст короткий и не содержит глаголов действия
        if len(text_lower.split()) <= 10:
            # Проверяем на отсутствие глаголов запроса
            action_verbs = ['дай', 'хочу', 'приготовь', 'сделай', 'научи', 'покажи']
            has_action_verb = any(verb in text_lower for verb in action_verbs)
            
            if not has_action_verb:
                return True
        
        return False
    
    @staticmethod
    def detect_intent(text: str) -> dict:
        """Определяет намерение пользователя"""
        result = {
            'intent': 'unknown',
            'dish_name': '',
            'is_recipe_request': False,
            'is_products_list': False,
            'confidence': 0.0
        }
        
        if not text:
            return result
        
        # Проверяем запрос рецепта
        if IntentDetector.is_recipe_request(text):
            result['intent'] = 'recipe_request'
            result['is_recipe_request'] = True
            result['dish_name'] = IntentDetector.extract_dish_name(text)
            result['confidence'] = 0.9
            return result
        
        # Проверяем список продуктов
        if IntentDetector.is_products_list(text):
            result['intent'] = 'products_list'
            result['is_products_list'] = True
            result['confidence'] = 0.8
            return result
        
        # Неизвестное намерение
        return result