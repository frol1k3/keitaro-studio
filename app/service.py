import hashlib
import json
import re
import secrets

from app.keitaro import KeitaroError


def version_for(stream: dict) -> str:
    data = {"updated_at": stream.get("updated_at"), "offers": [
        {"offer_id": o["offer_id"], "share": o["share"], "state": o.get("state", "active")}
        for o in stream.get("offers", [])
    ]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def campaign_alias(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24]
    return (slug or "campaign") + "-" + secrets.token_hex(3)


async def create_campaign(client, *, name: str, country: str, offer_id: int,
                          domain_id: int, group_id: int, traffic_source_id: int,
                          prefix: str):
    catalog = await client.catalog()
    checks = (("offers", offer_id), ("domains", domain_id),
              ("groups", group_id), ("sources", traffic_source_id))
    for kind, item_id in checks:
        if not any(int(item["id"]) == item_id for item in catalog[kind]):
            raise KeitaroError(422, f"ID {item_id} отсутствует в активном списке {kind}")
    full_name = name if name.startswith(prefix) else prefix + name
    if len(full_name) > 100:
        raise KeitaroError(422, "Название кампании с префиксом не должно превышать 100 символов")
    campaign = await client.request("POST", "campaigns", json={
        "alias": campaign_alias(full_name), "name": full_name,
        "type": "position", "state": "active", "domain_id": domain_id,
        "group_id": str(group_id), "traffic_source_id": traffic_source_id,
    })
    campaign_id = int(campaign["id"])
    try:
        await client.request("POST", "streams", json={
            "campaign_id": campaign_id, "schema": "redirect", "type": "forced",
            "name": f"{country} → Google", "position": 1, "state": "active",
            "action_type": "http", "action_payload": "https://www.google.com/",
            "collect_clicks": True,
            "filters": [{"name": "country", "mode": "accept", "payload": [country]}],
        })
        await client.request("POST", "streams", json={
            "campaign_id": campaign_id, "schema": "landings", "type": "default",
            "name": "Остальные → оффер", "position": 2, "state": "active",
            "action_type": "http", "collect_clicks": True,
            "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
        })
    except Exception:
        # Keitaro archives campaigns, allowing recovery if a partial setup fails.
        try:
            await client.request("DELETE", f"campaigns/{campaign_id}")
        except KeitaroError:
            pass
        raise
    return await client.request("GET", f"campaigns/{campaign_id}")


async def get_campaign_detail(client, campaign_id: int):
    campaign = await client.request("GET", f"campaigns/{campaign_id}")
    streams = await client.request("GET", f"campaigns/{campaign_id}/streams")
    offers = await client.request("GET", "offers")
    names = {int(o["id"]): o["name"] for o in offers}
    for stream in streams:
        stream["version"] = version_for(stream)
        stream["offers"] = [{**o, "name": names.get(int(o["offer_id"]), f"#{o['offer_id']}")}
                             for o in stream.get("offers", [])]
    return {"campaign": campaign, "streams": streams}


async def update_offers(client, campaign_id: int, stream_id: int,
                        offers: list[dict], expected_version: str):
    streams = await client.request("GET", f"campaigns/{campaign_id}/streams")
    stream = next((s for s in streams if int(s["id"]) == stream_id), None)
    if stream is None:
        raise KeitaroError(404, "Поток не принадлежит этой кампании")
    if version_for(stream) != expected_version:
        raise KeitaroError(409, "Поток изменился в Keitaro. Обновите страницу")
    if stream.get("schema") != "landings":
        raise KeitaroError(422, "Этот поток не поддерживает офферы")
    ids = [x["offer_id"] for x in offers]
    if len(ids) != len(set(ids)):
        raise KeitaroError(422, "Оффер не может повторяться")
    active = [x for x in offers if x.get("state", "active") == "active"]
    if not active or sum(x["share"] for x in active) != 100 or any(x["share"] < 1 for x in active):
        raise KeitaroError(422, "Сумма долей должна быть 100%, каждая доля — от 1%")
    existing = await client.request("GET", "offers")
    active_ids = {int(x["id"]) for x in existing if x.get("state") == "active"}
    existing_ids = {int(x["offer_id"]) for x in stream.get("offers", [])}
    if not set(ids).issubset(active_ids | existing_ids):
        raise KeitaroError(422, "Один из офферов отсутствует или выключен")
    payload = [{"offer_id": x["offer_id"], "share": x["share"], "state": x.get("state", "active")}
               for x in offers]
    await client.request("PUT", f"streams/{stream_id}", json={"offers": payload})
    return await get_campaign_detail(client, campaign_id)
