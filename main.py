from asyncio import new_event_loop, set_event_loop, sleep

from aiohttp.client import ClientSession

from random import randrange
from datetime import datetime
from xml.etree import ElementTree as xml
import logging
import shutil

import json

class EAT():
    
    LIST_URL = "https://tender-cache-api.agregatoreat.ru/api/TradeLot/list-published-trade-lots"
    LAST_UID_PARAM_NAME = "UID последнего запроса"

    CONFIG_FILE = "config.json"
    CONFIG_TEMPLATE_PATH = "Templates/config_default.json"

    def __init__(self) -> None:
        try: 
            with open(self.CONFIG_FILE, mode='r', encoding="UTF-8") as f:
                self.data = json.load(f)
        except:
            shutil.copyfile(self.CONFIG_TEMPLATE_PATH, self.CONFIG_FILE)
            with open(self.CONFIG_FILE, mode='r', encoding="UTF-8") as f:
                self.data = json.load(f)

        self.log("Файл с настройками успешно считан")

        self.token = self.get_param("ЕАТ", "Токен")
        self.inn = self.get_param("ЕАТ", "ИНН")
        self.price = self.get_param("ЕАТ", "Ставка")
        self.nds = self.get_param("ЕАТ", "НДС")
        self.procedure = self.get_param("ЕАТ", "Ключевая фраза")
        self.excluded_procedures = self.get_param("ЕАТ", "Исключаемые процедуры")
        self.extSystem = self.get_param("Параметры поставщика", "Номер системы")
        
        self.last_uid = self.get_param("Переменные", "UID последнего запроса")
        self.main_uid_part = self.get_param("Переменные", "Основная часть стартового Request UID")
        self.eval_uid_part = self.get_param("Переменные", "Расчетная часть стартового Request UID")

        self.list_url = self.get_param("Переменные", "URL JSON API списка закупок")
        self.info_url = self.get_param("Переменные", "URL XML API получения информации о закупке")
        self.result_url = self.get_param("Переменные", "URL XML API подтверждения запроса")
        self.add_proposal_url = self.get_param("Переменные", "URL XML API создание предложения")
        
        self.load_info_file()
        self.load_result_file()
        self.load_proposal_file()
        self.load_proposal_detail_file()

        debug_text = self.get_param("Общие", "Выводить в консоль отладочную инфорацию?")
        self.is_debug = False if debug_text == "Нет" else "Да"

        self.json_body = {
            "page": 1,
            "size": 5,
            "searchText": self.procedure,
            "customerNameOrInn": self.inn,
            "isEatOnly": True,
            "sort": [
                {
                    "fieldName": "publishDate",
                    "direction": 2
                }
            ]
        }

        self.json_headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

        self.xml_headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'text/xml',
            'Accept': 'text/xml'
        }

        self.log("Все параметры успешно считаны")

    def load_info_file(self):
        path = self.get_param("Переменные", "XML файл с запросом на получение информации о закупке")
        body = open(path, "r", encoding="UTF-8").read()
        body = body.replace('SYSTEM_NUMBER_PARAM', str(self.extSystem))
        self.info_body = body

    def load_result_file(self):
        path = self.get_param("Переменные", "XML файл с запросом на получение результата")
        body = open(path, "r", encoding="UTF-8").read()
        body = body.replace('SYSTEM_NUMBER_PARAM', str(self.extSystem))
        self.result_body = body

    def load_proposal_file(self):
        path = self.get_param("Переменные", "XML файл с запросом на добавление предложения")
        body = open(path, "r", encoding="UTF-8").read()
        body = body.replace('SYSTEM_NUMBER_PARAM', str(self.extSystem))

        body = self.replace_template("Параметры поставщика", "Название компании", 'SUPPLIER_NAME_PARAM', body)
        body = self.replace_template("Параметры поставщика", "ИНН", 'SUPPLIER_INN_PARAM', body)
        body = self.replace_template("Параметры поставщика", "КПП", 'SUPPLIER_KPP_PARAM', body)
        body = self.replace_template("Параметры поставщика", "ОГРН", 'SUPPLIER_OGRN_PARAM', body)
        body = self.replace_template("Параметры поставщика", "Адрес", 'SUPPLIER_ADDRESS', body)
        body = self.replace_template("Параметры поставщика", "Email", 'SUPPLIER_EMAIL', body)
        body = self.replace_template("Параметры поставщика", "Номер телефона", 'SUPPLIER_PHONE', body)
        body = self.replace_template("Параметры поставщика", "Адрес", 'SUPPLIER_ADDRESS', body)
        body = self.replace_template("ЕАТ", "Название файла", 'FILE_NAME_PARAM', body)
        body = self.replace_template("ЕАТ", "Ссылка на файл", 'FILE_REF_PARAM', body)

        self.proposal_body = body

    def load_proposal_detail_file(self):
        path = self.get_param("Переменные", "XML файл с предложением по позиции")
        self.proposal_detail_body = open(path, "r", encoding="UTF-8").read()

    def get_param(self, header: str, name: str):
        try:
            param = self.data[header][name]
            if param == "" or param is None:
                raise InterruptedError()
        except:
            raise InterruptedError(f"Не удалось найти поле [{header}][{name}] в настройках")
        return param
    
    def replace_template(self, header, name, template_name, text) -> str:
        return text.replace(template_name, self.get_param(header=header, name=name))

    async def start(self):
        print("Начинаю поиск закупок...")
        while True:
            async with ClientSession(trust_env = True) as client:
                try:
                    async with client.post(self.list_url, 
                                           headers=self.json_headers, 
                                           json=self.json_body) as response:
                        #if self.is_debug:
                        self.start_time = datetime.now()

                        result = await response.json()

                        if "items" not in result:
                            continue

                        list = result["items"]
                        for item in list:
                            number = item["tradeNumber"]
                            winnerId = item["winnerId"]
                            if number not in self.excluded_procedures and winnerId is None:
                                self.log(f"Была найдена закупка с номером {number}")
                                info = await self.get_info(number)
                                if info is not None:
                                    await self.add_proposal(info)
                            elif winnerId is not None and self.is_debug:
                                self.log(f"Была найдена закупка, но поставщик уже был выбран")
                            elif self.is_debug:
                                self.log(f"Была найдена закупка, но она находится в списке исключенных")

                except Exception as e:
                    self.log(e)
                    continue

    async def save_param(self, name: str, header: str, value):
        with open(self.CONFIG_FILE, mode='r', encoding="UTF-8") as f:
            data = json.load(f)

        with open(self.CONFIG_FILE, mode='w', encoding="UTF-8") as f:
            data[header][name] = value
            json.dump(data, f, ensure_ascii=False, indent=4)

    async def load_data_from_file(self, body: str, uid:int = None) -> (str, int):
        
        eval_part = int(self.eval_uid_part)
        temp = eval_part
        if uid is None:
            temp += self.last_uid
        else:
            temp += uid

        new_number = f"{self.main_uid_part}{eval_part + temp}"

        body = body.replace("REQUEST_NUMBER_PARAM", new_number)
        self.last_uid += 1
        await self.save_param(self.LAST_UID_PARAM_NAME, "Переменные", self.last_uid)
        return (body, self.last_uid - 1)

    def log(self, message: str):
        print(f"[{datetime.now()}] {message}")

    async def get_info(self, number: int) -> str:
        async with ClientSession(trust_env = True) as client:
            headers = self.xml_headers
            info_body, request_uid = await self.load_data_from_file(self.info_body)
            info_body = info_body.replace('ORDER_NUMBER_PARAM', str(number))

            async with client.post(self.info_url, 
                                   headers=headers, 
                                   data=info_body) as response:
                if self.is_debug:
                    self.log(f"\n[POST] {self.info_url}, status = {response.status}")
                    self.log(await response.text())
            return await self.get_result(request_uid)

    async def get_result(self, uid: int) -> str:
        await sleep(0.5)
        async with ClientSession(trust_env = True) as client:
            is_processing = True
            while is_processing:
                result_body, _ = await self.load_data_from_file(self.result_body, uid)
                async with client.post(self.result_url, 
                                       headers=self.xml_headers, 
                                       data=result_body) as response:
                    text = await response.text()

                    if text == "":
                        self.log("У запроса не было тела")
                        await sleep(0.1)
                        #continue
                        break
                    
                    result = xml.fromstring(text)

                    if self.is_debug:
                        self.log(f"[POST] {self.result_url}, status = {response.status}")
                        self.log(text + '\n')

                    state = result[1].text

                    if state != "processing":
                        is_processing = False
                    else:
                        await sleep(0.05)
            return result

    async def add_proposal(self, xml_order_info) -> str:

        del xml_order_info[2][3]

        xml_order_info = xml_order_info[2]

        headers = self.xml_headers
        body, request_uid = await self.load_data_from_file(self.proposal_body)
        
        products = ""
        detail_template, _ = await self.load_data_from_file(self.proposal_detail_body, -1)
        number = 1
        index = 0
        for element in xml_order_info:
            if self.is_debug:
                print(element)

            if element.tag == "{http://agregatoreat.ru/eat/}Product":
                temp = detail_template.replace("SEQUENCE_NUMBER_PARAM", str(number)) #TODO
                number += 1

                temp = temp.replace("PRICE_PARAM", str(self.price))
                temp = temp.replace("NDS_PARAM", str(self.nds))
                products += temp

                param = element.find('{http://agregatoreat.ru/eat/}description')
                if param is None:
                    param = xml.Element("{http://agregatoreat.ru/eat/}description")
                    param.text = "test description"
                    element.insert(4, param)

                await self.remove_xml_node(element, '{http://agregatoreat.ru/eat/}images')
                await self.remove_xml_node(element, '{http://agregatoreat.ru/eat/}countryOfOrigin')
                await self.remove_xml_node(element, '{http://agregatoreat.ru/eat/}priceOption')
                await self.remove_xml_node(element, '{http://agregatoreat.ru/eat/}availableVolume')

                param = element.find('{http://agregatoreat.ru/eat/}cost')
                param.text = param.text.replace(',','')              
                
            index += 1
        
        if self.is_debug:
            self.log("\nПолученный список products" + products + "\n")

        max_cost = xml_order_info.find('{http://agregatoreat.ru/eat/}maxOrderCost')
        if max_cost is not None:
            max_cost.text = max_cost.text.replace(',','')

        seller = xml_order_info.find('.//{http://agregatoreat.ru/eat/}sellerRef')

        ogrn = xml.Element("{http://agregatoreat.ru/eat/}OGRN")
        ogrn.text = "0000000000000"
        seller.insert(2, ogrn)

        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}DeliveryAddress')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}trusteeFlag')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}additionalConditions')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}isSpecificSupplier')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}extNumber')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}attachments')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}notificationPrintForm')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}purchaseIdentificationСode')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}documentationRequired')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}documentationRequirements')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}isWinnerNDScounting')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}contractTermDate')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}PriceTrends')
        await self.remove_xml_node(xml_order_info, '{http://agregatoreat.ru/eat/}attachments')

        trends = xml_order_info.find("{http://agregatoreat.ru/eat/}PriceTrends")
        if trends is not None:
            xml_order_info.remove(trends)

        order_info = ""
        for element in xml_order_info:
            if element.tag != "{http://agregatoreat.ru/eat/}PriceTrends":
                order_info += xml.tostring(element, encoding='unicode')
        order_info = order_info.replace("ns0", "eat")

        if self.is_debug:
            self.log(f"Информация о закупке: {order_info}")

        body = body.replace('ORDER_INFO_PARAM', order_info)
        body = body.replace('PRODUCTS_REF_PARAM', products)
        body = body.replace('\n', '').replace('\t', '')

        if self.is_debug:
            self.log(f"Полученное тело запроса на добавление предложения: {body}\n")

        async with ClientSession(trust_env = True) as client:
            async with client.post(self.add_proposal_url, 
                                   headers=headers, 
                                   data=body) as response:
                result = await response.text()
                if self.is_debug:
                    self.log(f"\n[POST] {self.info_url}, status = {response.status}")
                    self.log(result + "\n")
            if "violations" not in result:
                end = datetime.now()
                self.log(f"Длительность подачи предложения: {end - self.start_time}")

                order_number = xml_order_info.find(".//{http://agregatoreat.ru/eat/}OrderNumber").text
                self.excluded_procedures.append(order_number)
                await self.save_param("Исключаемые процедуры", "ЕАТ", self.excluded_procedures)
                # body = await self.get_result(request_uid)

                # if body.find("{http://agregatoreat.ru/eat/}ProcessingState"):
                #     print(f"Успешно подано предложение на закупку {number}")

                if self.is_debug:
                    self.log(body)
                
    async def remove_xml_node(self, root, param_name):
        param = root.find(param_name)
        if param is not None:
            root.remove(param)

if __name__ == '__main__':
    loader = EAT()
    loop = new_event_loop()
    set_event_loop(loop)

    loop.run_until_complete(loader.start())