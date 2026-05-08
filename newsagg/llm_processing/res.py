#!/usr/bin/env python3
"""
Скрипт для классификации новостных заголовков и анализа текстов с использованием Ollama
"""

import os
import argparse
import requests
import json
import pandas as pd
from typing import Dict, List, Any


def load_data(path: str) -> Dict[str, List[str]]:
    """
    Загружает данные из JSON файла
    """
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}  # Пустой словарь, если файла нет


def save_data(data: Dict[str, Any], path: str) -> None:
    """
    Сохраняет данные в JSON файл
    """
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def query_ollama(model: str, task_prompt: str, content: str) -> str:
    """
    Отправляет запрос к локальной модели Ollama
    """
    url = "http://localhost:11434/api/chat"
    temperature = 0.5
    max_tokens = -1

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": task_prompt},
            {"role": "user", "content": content}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }

    try:
        response = requests.post(url, json=payload, timeout=60)

        if response.status_code == 200:
            result = response.json()
            return result["message"]["content"]
        else:
            return f"Ошибка: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Ошибка подключения: {str(e)}"


def load_classification_prompt(prompt_file: str) -> str:
    """
    Загружает промпт для классификации из файла
    """
    if not os.path.exists(prompt_file):
        raise FileNotFoundError(f"Файл с промптом {prompt_file} не найден")

    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read()


def process_dataframe(csv_file: str) -> pd.DataFrame:
    """
    Обрабатывает CSV файл с новостями
    """
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"CSV файл {csv_file} не найден")

    # Загружаем данные
    data = pd.read_csv(csv_file, header=None, index_col=0, skip_blank_lines=True)

    # Переименовываем колонки
    data.rename(columns={
        1: "title",
        2: "text",
        3: "shorten_text",
        4: "link",
        5: "posted",
        6: "scanned",
        7: "processed",
        8: "source_id"
    }, inplace=True)

    # Удаляем пустые строки
    data = data.dropna()

    # Обрабатываем заголовки
    for i in range(len(data)):
        if i < len(data) and pd.notna(data.iloc[i, 0]):
            title_part = str(data.iloc[i, 1]).split('.')[0] + "|"
            data.iloc[i, 0] = title_part

    return data


def parse_model_output(model_output: str) -> tuple:
    """
    Парсит вывод модели для извлечения категорий и новостей
    """
    sentences = model_output.split("|")
    categories = []
    news = []

    for sentence in sentences:
        if "-" in sentence:
            parts = sentence.split("-", 1)  # Разделяем только по первому дефису
            if len(parts) == 2:
                category = parts[0].strip()
                news_items = [item.strip() for item in parts[1].split(";") if item.strip()]

                categories.append(category)
                news.append(news_items)

    return categories, news


def main():
    """
    Основная функция скрипта
    """
    parser = argparse.ArgumentParser(description='Классификация и анализ новостей с использованием Ollama')
    parser.add_argument('--csv', type=str, default='aggregator_newsitem.csv',
                        help='Путь к CSV файлу с новостями')
    parser.add_argument('--class_prompt', type=str, default='запрос_классификация.txt',
                        help='Файл с промптом для классификации')
    parser.add_argument('--analysis_prompt', type=str, default='Запрос_анализ.txt',
                        help='Файл с промптом для анализа')
    parser.add_argument('--output', type=str, default='respond.txt',
                        help='Файл для сохранения результатов анализа')
    parser.add_argument('--data_file', type=str, default='dat.json',
                        help='JSON файл для хранения классифицированных данных')
    parser.add_argument('--model', type=str, default='akdengi/saiga-llama3-8b',
                        help='Название модели Ollama')
    parser.add_argument('--limit', type=int, default=10,
                        help='Лимит новостей для обработки')

    args = parser.parse_args()

    try:
        # Загружаем промпты
        #print("📖 Загружаю промпты...")
        class_prompt = load_classification_prompt(args.class_prompt)
        analysis_prompt = load_classification_prompt(args.analysis_prompt)

        # Обрабатываем данные
        #print("📊 Загружаю и обрабатываю данные...")
        data = process_dataframe(args.csv)

        # Подготавливаем заголовки для классификации
        existing_groups = "Протесты в Грузии, Сделка по Газе, Война на Украине"
        titles_sample = "".join(data.iloc[1:min(7, len(data)), 0].astype(str))

        content = f"Существующие группы: {{{existing_groups}}}\n"
        content += f"ЗАГОЛОВКИ: {{{titles_sample}}}\n"
        content += "НАЧИНАЙ ОТВЕТ:"

        # Выполняем классификацию
        print("🤖 Выполняю классификацию новостей...")
        model_output = query_ollama(args.model, class_prompt, content)

        if model_output.startswith("Ошибка"):
            print(f" Ошибка при классификации: {model_output}")
            return

        #print("✅ Классификация завершена")

        # Парсим результат классификации
        categories, news = parse_model_output(model_output)

        # Сохраняем результаты классификации
        data_json = load_data(args.data_file)

        for i, category in enumerate(categories):
            if i < len(news):
                if category not in data_json:
                    data_json[category] = []

                # Добавляем новости в категорию
                for news_item in news[i]:
                    if news_item not in data_json[category]:
                        data_json[category].append(news_item)

        save_data(data_json, args.data_file)
        #print(f"💾 Результаты классификации сохранены в {args.data_file}")

        # Выполняем анализ для категорий с достаточным количеством новостей
        #print("🔍 Выполняю анализ новостей...")
        analysis_results = {}

        for category, news_items in data_json.items():
            if len(news_items) > 3:  # Достаточная экспозиция для анализа
                print(f"Анализирую категорию: {category}")

                # Создаем паттерн для поиска в текстах
                pattern = '|'.join(map(str, news_items))
                mask = data["text"].str.contains(pattern, case=False, na=False, regex=True)
                results = data[mask]["text"].tolist()

                if results:
                    messages = "{" + "|".join(results[:5]) + "}"  # Ограничиваем количество

                    # Выполняем анализ
                    analysis_result = query_ollama(args.model, analysis_prompt, messages)
                    analysis_results[category] = analysis_result

        # Сохраняем результаты анализа
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(analysis_results, f, ensure_ascii=False, indent=4)

        print(f"✅ Анализ завершен. Результаты сохранены в {args.output}")
        print("🎉 Скрипт успешно выполнен!")

    except FileNotFoundError as e:
        print(f"❌ Файл не найден: {e}")
    except Exception as e:
        print(f"❌ Произошла ошибка: {e}")


if __name__ == "__main__":
    main()