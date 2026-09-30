import json
import os
import re
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("MODEL", "gpt-5-nano")
API_KEY = os.getenv("OPENAI_API_KEY")

if not API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not configured.")

client = OpenAI(api_key=API_KEY)

app = FastAPI(title="GenAI Sales Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your deployed frontend domain in production.
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

MAX_FILE_BYTES = 15 * 1024 * 1024


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def build_schema_profile(df: pd.DataFrame) -> dict[str, list[str]]:
    schema = {"metrics": [], "dimensions": []}

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            schema["metrics"].append(col)
        else:
            schema["dimensions"].append(col)

    return schema


def safe_json(text: str) -> dict[str, Any]:
    text = re.sub(r"```json|```", "", text).strip()
    match = re.search(r"\{.*\}", text, re.S)

    if not match:
        raise ValueError("The AI model did not return valid JSON.")

    return json.loads(match.group())


def apply_filters(
    df: pd.DataFrame,
    filters: list[dict[str, Any]]
) -> pd.DataFrame:

    d = df.copy()

    for item in filters:
        col = item["column"]
        op = item["operator"]
        val = item["value"]

        if col not in d.columns:
            raise ValueError(f"Unknown filter column: {col}")

        if pd.api.types.is_string_dtype(d[col]):
            series = d[col].astype(str).str.lower().str.strip()

            if isinstance(val, list):
                vals = [str(v).lower().strip() for v in val]
            else:
                vals = str(val).lower().strip()

        else:
            series = d[col]
            vals = val

        if op == "=":
            d = d[
                series.isin(vals)
                if isinstance(vals, list)
                else series == vals
            ]

        elif op == "!=":
            d = d[series != vals]

        elif op == ">":
            d = d[series > vals]

        elif op == "<":
            d = d[series < vals]

        elif op == ">=":
            d = d[series >= vals]

        elif op == "<=":
            d = d[series <= vals]

        elif op == "in":
            d = d[series.isin(vals)]

        else:
            raise ValueError(f"Unsupported filter operator: {op}")

    return d


def aggregate(series: pd.Series, operation: str) -> float:

    if operation == "sum":
        return float(series.sum())

    if operation in ("avg", "mean"):
        return float(series.mean())

    if operation == "count":
        return float(series.count())

    if operation == "min":
        return float(series.min())

    if operation == "max":
        return float(series.max())

    raise ValueError(f"Unsupported aggregation: {operation}")


def compute(
    df: pd.DataFrame,
    intent: dict[str, Any]
) -> pd.Series:

    d = df.copy()

    time = intent.get("time") or {}

    if time.get("column"):

        col = time["column"]
        value = time.get("value")

        if col not in d.columns:
            raise ValueError(f"Unknown time column: {col}")

        if isinstance(value, list):
            d = d[d[col].between(value[0], value[1])]

        elif value is not None:
            d = d[d[col] == value]

    d = apply_filters(d, intent.get("filters", []))

    aggregation = intent.get("aggregation", "sum")
    order = intent.get("order", "desc")
    limit = intent.get("limit") or 5

    dimensions = intent.get("dimensions", [])
    metrics = intent.get("metrics", [])

    dimension = dimensions[0] if dimensions else None

    metric = (
        None
        if aggregation == "count"
        else (metrics[0] if metrics else None)
    )

    if metric and metric not in d.columns:
        raise ValueError(f"Unknown metric: {metric}")

    if intent.get("intent_type") == "yoy":

        if (
            not time.get("column")
            or not isinstance(time.get("value"), list)
        ):
            raise ValueError("YoY analysis requires two time values.")

        y1, y2 = time["value"]
        tcol = time["column"]

        d1 = d[d[tcol] == y1]
        d2 = d[d[tcol] == y2]

        v1 = (
            len(d1)
            if aggregation == "count"
            else aggregate(d1[metric], aggregation)
        )

        v2 = (
            len(d2)
            if aggregation == "count"
            else aggregate(d2[metric], aggregation)
        )

        yoy = ((v2 - v1) / v1 * 100) if v1 else None

        return pd.Series({
            str(y1): v1,
            str(y2): v2,
            "Delta": v2 - v1,
            "YoY %": yoy if yoy is not None else float("nan"),
        })

    if dimension is None:

        if aggregation == "count":
            return pd.Series({"Total": len(d)})

        return pd.Series({
            "Total": aggregate(d[metric], aggregation)
        })

    if dimension not in d.columns:
        raise ValueError(f"Unknown dimension: {dimension}")

    if aggregation == "count":

        result = d.groupby(dimension).size()

    else:

        result = d.groupby(dimension)[metric].agg(aggregation)

    return result.sort_values(
        ascending=(order == "asc")
    ).head(limit)


def format_value(value: Any) -> str | float | int:

    if pd.isna(value):
        return None

    value = float(value)

    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"

    if abs(value) >= 1_000:
        return f"{value:,.0f}"

    if value.is_integer():
        return f"{int(value):,}"

    return round(value, 2)


def build_rows(
    result: pd.Series
) -> list[dict[str, Any]]:

    return [
        {
            "label": str(index),
            "value": format_value(value)
        }
        for index, value in result.items()
    ]


def required_fields_for_intent(
    intent: dict[str, Any]
) -> set[str]:

    required: set[str] = set()

    intent_type = intent.get("intent_type")

    viz = (
        intent.get("visualization") or {}
    ).get("type")

    if intent_type in ("aggregation", "ranking"):
        required.add("aggregation")

    if intent_type == "ranking":
        required.update(["metrics", "dimensions"])

    if viz in ("pie", "bar", "line"):
        required.update(["metrics", "dimensions"])

    if viz == "hist":
        required.add("metrics")

    if intent_type == "yoy":
        required.update(["metrics", "time"])

    return required


def validate_required_fields(
    intent: dict[str, Any]
) -> list[str]:

    errors = []

    intent_type = intent.get("intent_type")

    metrics = intent.get("metrics", [])
    dimensions = intent.get("dimensions", [])

    time = intent.get("time") or {}

    viz = (
        intent.get("visualization") or {}
    ).get("type")

    agg = intent.get("aggregation")

    if intent_type == "aggregation":
        if agg != "count" and not metrics:
            errors.append("Aggregation requires a metric.")

    if intent_type == "ranking":

        if not metrics:
            errors.append("Ranking requires a metric.")

        if not dimensions:
            errors.append("Ranking requires a dimension.")

    if intent_type == "yoy":

        if not metrics:
            errors.append("YoY requires a metric.")

        if not time.get("column"):
            errors.append("YoY requires a time column.")

        if (
            not isinstance(time.get("value"), list)
            or len(time["value"]) != 2
        ):
            errors.append("YoY requires two time values.")

    if viz == "pie":

        if not metrics:
            errors.append("Pie chart requires a metric.")

        if not dimensions:
            errors.append("Pie chart requires a dimension.")

    if viz in ("bar", "line"):

        if not metrics:
            errors.append(
                f"{viz} chart requires a metric."
            )

        if not dimensions:
            errors.append(
                f"{viz} chart requires a dimension."
            )

    if viz == "hist" and not metrics:
        errors.append("Histogram requires a metric.")

    return errors


def compute_confidence(
    intent: dict[str, Any]
) -> tuple[float, list[str]]:

    score = 1.0
    reasons = []

    errors = validate_required_fields(intent)

    score -= 0.15 * len(errors)

    reasons.extend(errors)

    sources = intent.get("sources") or {}

    for field in required_fields_for_intent(intent):

        if sources.get(field) == "inferred":

            penalty = {
                "metrics": 0.15,
                "dimensions": 0.15,
                "aggregation": 0.10,
                "time": 0.15,
            }.get(field, 0)

            score -= penalty

            reasons.append(
                f"{field.capitalize()} was inferred, "
                "not explicitly specified."
            )

    score = round(
        max(min(score, 1.0), 0.0),
        2
    )

    return score, reasons


@lru_cache(maxsize=128)
def parse_intent(
    question: str,
    metrics: tuple[str, ...],
    dimensions: tuple[str, ...],
) -> dict[str, Any]:

    prompt = f"""
You convert a business analytics question into a structured intent.

Available metrics:
{list(metrics)}

Available dimensions:
{list(dimensions)}

Rules:
- Use ONLY the available column names.
- Never invent columns.
- If aggregation is count, metrics must be [].
- Return JSON only.
- Mark required fields as explicit or inferred in sources.

Schema:
{{
  "intent_type": "aggregation|ranking|comparison|yoy|trend|distribution|stats",
  "metrics": ["string"],
  "dimensions": ["string"],
  "filters": [
    {{
      "column": "string",
      "operator": "= | != | > | < | >= | <= | in",
      "value": "string | number | [string | number]"
    }}
  ],
  "time": {{
    "column": "string | null",
    "value": "number | [number, number] | null"
  }},
  "aggregation": "sum | avg | count | min | max",
  "order": "asc | desc",
  "limit": "number | null",
  "visualization": {{
    "type": "bar | line | pie | hist | none"
  }},
  "sources": {{
    "metrics": "explicit | inferred",
    "dimensions": "explicit | inferred",
    "aggregation": "explicit | inferred",
    "time": "explicit | inferred"
  }}
}}

User question:
{question}
"""

    response = client.responses.create(
        model=MODEL,
        input=prompt
    )

    return safe_json(response.output_text)


def generate_explanation(
    question: str,
    rows: list[dict[str, Any]],
) -> str:

    table = "\n".join(
        f"{row['label']}: {row['value']}"
        for row in rows
    )

    prompt = f"""
You are a senior business analyst.

Question:
{question}

Deterministically computed result:
{table}

Use ONLY the supplied result. Do not invent numbers.

Return a concise 2-4 sentence answer that:
- directly answers the question,
- highlights the most important result,
- mentions a useful business pattern only when directly supported,
- does not claim information that is not present.
"""

    response = client.responses.create(
        model=MODEL,
        input=prompt
    )

    return response.output_text.strip()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    question: str = Form(...),
):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="A file is required."
        )

    if not file.filename.lower().endswith(
        (".xlsx", ".xls")
    ):
        raise HTTPException(
            status_code=400,
            detail="Only Excel .xlsx or .xls files are supported."
        )

    content = await file.read()

    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum size is 15 MB."
        )

    temp_path = None

    try:

        suffix = Path(file.filename).suffix

        with NamedTemporaryFile(
            delete=False,
            suffix=suffix
        ) as temp:

            temp.write(content)
            temp_path = temp.name

        df = pd.read_excel(temp_path)

        df.columns = [
            normalize(c)
            for c in df.columns
        ]

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail="The Excel file is empty."
            )

        schema = build_schema_profile(df)

        intent = parse_intent(
            question.strip(),
            tuple(schema["metrics"]),
            tuple(schema["dimensions"]),
        )

        available = set(df.columns)

        for col in intent.get("metrics", []):

            if col not in available:
                raise ValueError(
                    f"AI selected an unavailable metric: {col}"
                )

        for col in intent.get("dimensions", []):

            if col not in available:
                raise ValueError(
                    f"AI selected an unavailable dimension: {col}"
                )

        for filt in intent.get("filters", []):

            if filt["column"] not in available:
                raise ValueError(
                    "AI selected an unavailable "
                    f"filter column: {filt['column']}"
                )

        time = intent.get("time") or {}

        if (
            time.get("column")
            and time["column"] not in available
        ):
            raise ValueError(
                "AI selected an unavailable "
                f"time column: {time['column']}"
            )

        confidence, reasons = compute_confidence(intent)

        if confidence < 0.5:
            raise HTTPException(
                status_code=422,
                detail=(
                    "The question is ambiguous. "
                    "Please specify the metric, dimension, "
                    "or time period."
                ),
            )

        result = compute(df, intent)

        rows = build_rows(result)

        answer = generate_explanation(
            question.strip(),
            rows
        )

        return {
            "question": question.strip(),
            "file_name": file.filename,
            "intent": intent,
            "confidence": confidence,
            "confidence_label": (
                "High"
                if confidence >= 0.8
                else "Medium"
                if confidence >= 0.5
                else "Low"
            ),
            "confidence_reasons": reasons,
            "answer": answer,
            "result": rows,
            "chart_type": (
                intent.get("visualization") or {}
            ).get("type", "none"),
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Analytics engine error: {str(exc)}"
        )

    finally:

        if temp_path:

            try:
                os.remove(temp_path)

            except OSError:
                pass
