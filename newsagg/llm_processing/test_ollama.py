import requests

response = requests.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen2.5:7b-instruct",
        "messages": [
            {
                "role": "user",
                "content": "Кратко перескажи новость: В Москве открылся новый технопарк."
            }
        ],
        "stream": False
    }
)

print(response.json()["message"]["content"])