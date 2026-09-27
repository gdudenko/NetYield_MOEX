"""
Диагностический скрипт: смотрим, что реально возвращает ЦБ РФ.
"""

import requests
import xml.etree.ElementTree as ET


def debug_cbr_response():
    url = "http://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"

    soap_body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <MainInfoXML xmlns="http://web.cbr.ru/" />
  </soap:Body>
</soap:Envelope>"""

    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': 'http://web.cbr.ru/MainInfoXML',
    }

    try:
        print("Отправляю запрос к ЦБ РФ...")
        response = requests.post(
            url, data=soap_body, headers=headers, timeout=15
        )
        print(f"Статус: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        print()
        print("=" * 80)
        print("СЫРОЙ ОТВЕТ:")
        print("=" * 80)
        content = response.content.decode('utf-8', errors='replace')
        print(content)
        print("=" * 80)

        # Пробуем распарсить
        print("\nПАРСИНГ ЭЛЕМЕНТОВ:")
        print("=" * 80)
        root = ET.fromstring(response.content)

        # Выводим все элементы с их тегами и текстом
        for elem in root.iter():
            tag = elem.tag
            text = elem.text.strip() if elem.text else '<пусто>'
            attrs = elem.attrib
            print(f"Тег: {tag}")
            print(f"  Текст: {text}")
            if attrs:
                print(f"  Атрибуты: {attrs}")
            print()

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    debug_cbr_response()
