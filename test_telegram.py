import requests

bot_token = "8178548352:AAFVfRv_GiyKDCCBL8B5iJyA7Rv1D1ASreE" 
chat_id = "7266837472"  
text = "테스트 메시지"

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
resp = requests.post(url, data={"chat_id": chat_id, "text": text})

print("응답 코드:", resp.status_code)
print("응답 내용:", resp.text)