import httpx


class KeitaroError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class KeitaroClient:
    def __init__(self, base_url: str, api_key: str, transport=None):
        self.base_url = base_url.rstrip("/") + "/admin_api/v1"
        self.api_key = api_key
        self.transport = transport

    async def request(self, method: str, path: str, *, json=None, params=None):
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Api-Key": self.api_key, "Accept": "application/json"},
            timeout=20.0,
            transport=self.transport,
        ) as client:
            try:
                response = await client.request(method, path.lstrip("/"), json=json, params=params)
            except httpx.RequestError as exc:
                raise KeitaroError(502, "Не удалось соединиться с Keitaro") from exc
        if response.status_code >= 400:
            # Do not forward arbitrary upstream bodies: some installations echo submitted data.
            codes = {400: "Keitaro отклонил параметры", 401: "Неверный API ключ Keitaro",
                     402: "Admin API недоступен в этой лицензии", 404: "Объект не найден в Keitaro",
                     406: "Keitaro отклонил данные потока"}
            raise KeitaroError(response.status_code if response.status_code < 500 else 502,
                               codes.get(response.status_code, "Ошибка Keitaro"))
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise KeitaroError(502, "Keitaro вернул не JSON") from exc

    async def catalog(self):
        domains = await self.request("GET", "domains")
        groups = await self.request("GET", "groups", params={"type": "campaigns"})
        sources = await self.request("GET", "traffic_sources")
        offers = await self.request("GET", "offers")
        return {"domains": [x for x in domains if x.get("state") == "active"],
                "groups": groups,
                "sources": [x for x in sources if x.get("state") == "active"],
                "offers": [x for x in offers if x.get("state") == "active"]}

