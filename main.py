import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Решись Авиа — прогноз спроса")
templates = Jinja2Templates(directory="templates")

# ---------- загрузка данных ----------
FORECAST = pd.read_csv("data/Рыжова Екатерина Дмитриевна_my_forecast.csv")
ROUTES = pd.read_csv("data/routes.csv")

# нормализуем названия колонок на всякий случай
FORECAST.columns = [c.strip() for c in FORECAST.columns]
ROUTES.columns = [c.strip() for c in ROUTES.columns]

QUANTILES = [f"0.{i}" for i in range(1, 10)]  # 0.1 ... 0.9

# ---------- вспомогательные ----------
def find_route_row(origin: str, destination: str, date: str):
    route = f"{origin}-{destination}"
    row = FORECAST[(FORECAST["route"] == route) & (FORECAST["date"] == date)]
    if row.empty:
        raise HTTPException(404, f"Нет прогноза для {route} на {date}")
    return row.iloc[0]

def route_params(route: str):
    r = ROUTES[ROUTES["route"] == route]
    if r.empty:
        raise HTTPException(404, f"Нет параметров маршрута {route}")
    r = r.iloc[0]
    return float(r["base_price"]), float(r["price_sensitivity"])

def demand_at_price(base_demand: float, price: float,
                    base_price: float, sens: float) -> float:
    return base_demand - sens * (price - base_price)

class ForecastRequest(BaseModel):
    origin: str
    destination: str
    date: str
    price: float

class ForecastResponse(BaseModel):
    seats: int
    want: float
    will_buy: int
    scenarios: List[dict]   # для графика

# ---------- API ----------
@app.post("/api/forecast", response_model=ForecastResponse)
def forecast(req: ForecastRequest):
    route = f"{req.origin}-{req.destination}"
    row = find_route_row(req.origin, req.destination, req.date)
    base_price, sens = route_params(route)
    seats = int(row["seats"])

    # медиана
    med_base = float(row["0.5_base_demand"])
    want = demand_at_price(med_base, req.price, base_price, sens)
    will_buy = int(min(seats, max(0, want)))

    # сценарии 0.1 ... 0.9 для графика
    scenarios = []
    for q in QUANTILES:
        col = f"{q}_base_demand"
        if col not in row:
            continue
        bd = float(row[col])
        d = demand_at_price(bd, req.price, base_price, sens)
        scenarios.append({
            "quantile": float(q),
            "want": round(d, 2),
            "will_buy": int(min(seats, max(0, d)))
        })

    return ForecastResponse(
        seats=seats,
        want=round(want, 2),
        will_buy=will_buy,
        scenarios=scenarios
    )

# ---------- страница ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # список маршрутов и дат для выпадающих списков
    routes = sorted(FORECAST["route"].unique().tolist())
    dates = sorted(FORECAST["date"].unique().tolist())
    return templates.TemplateResponse("index.html", {
        "request": request,
        "routes": routes,
        "dates": dates,
    })
