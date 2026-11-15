"""SNAPBACK's team of agents, as one roster (GET /agents, and the War Room page).

One card per agent: its name, its team, its job in one plain line, the tools and data it uses,
what runs it (a Claude model, or code) and what it never does. `kinds` ties a card to the
sub-agent names (`casework.AGENT_NAMES`) and the timeline step kinds (`timeline.py`) that
belong to it, and `checks` to the report's checks, so a page can light the right desk for a
case. A test fails when a sub-agent name or a step kind has no card.

The roster is a view of the product as it is. It runs nothing, changes no prompt and sets no
result: `snapback.verdict.decide` is the only place a verdict is chosen, and the Decider card
says so.

`uv run python -m snapback.agent.roster` prints the copy the web app ships for the static
front end (apps/web/src/warroom/roster.json).
"""

import json
from typing import Literal

from pydantic import BaseModel

Team = Literal["planner", "scam_check", "listing_help", "decider"]
Model = Literal["Claude Sonnet", "Claude Haiku", "code"]
Lang = Literal["en", "es"]

TEAM_ORDER: tuple[Team, ...] = ("planner", "scam_check", "listing_help", "decider")


class AgentCard(BaseModel):
    id: str
    name: str
    team: Team
    job: str  # one plain line
    tools: list[str]  # named tools and data sources, shown as chips
    model: Model
    never: list[str]  # things it never does
    # Set when the agent sits behind a switch: the words say when it is there.
    availability: str | None = None
    # Sub-agent names and timeline step kinds that belong to this card.
    kinds: list[str] = []
    # The report's checks this card answers for (the ids in apps/web/src/case/answer.ts).
    checks: list[str] = []


class TeamInfo(BaseModel):
    id: Team
    name: str
    about: str


class Roster(BaseModel):
    """`GET /agents`: the teams in floor order and every agent's card."""

    lang: Lang
    teams: list[TeamInfo]
    agents: list[AgentCard]


_TEAMS: dict[Team, dict[Lang, tuple[str, str]]] = {
    "planner": {
        "en": ("Planner", "Writes the plan and hands the work out."),
        "es": ("Planificador", "Escribe el plan y reparte el trabajo."),
    },
    "scam_check": {
        "en": ("Scam check team", "Each one checks one thing about the ad and reports back."),
        "es": (
            "Equipo de comprobación",
            "Cada uno comprueba una cosa del anuncio e informa.",
        ),
    },
    "listing_help": {
        "en": ("Listing help team", "Finds safer homes and gets you ready for a tour."),
        "es": (
            "Equipo de ayuda con anuncios",
            "Busca casas más seguras y le prepara para una visita.",
        ),
    },
    "decider": {
        "en": ("Decider", "Code. The only one that sets the verdict."),
        "es": ("Decisor", "Código. El único que fija el resultado."),
    },
}

# Each card: the fixed facts, then its words in each language (name, job, tools, never,
# availability). Tool names that are product names stay as they are in both languages.
_CARDS: list[dict] = [
    {
        "id": "planner",
        "team": "planner",
        "model": "Claude Sonnet",
        "kinds": [],
        "checks": [],
        "en": {
            "name": "Planner",
            "job": "Writes the plan and the to-do list, then hands each check to its agent.",
            "tools": ["deepagents plan", "To-do list", "Case notes"],
            "never": ["Sets the verdict", "Changes a fact a check found"],
        },
        "es": {
            "name": "Planificador",
            "job": "Escribe el plan y la lista de tareas, y reparte cada comprobación.",
            "tools": ["Plan de deepagents", "Lista de tareas", "Notas del caso"],
            "never": ["Fija el resultado", "Cambia un dato que halló una comprobación"],
        },
    },
    {
        "id": "rules",
        "team": "scam_check",
        "model": "code",
        "kinds": ["claims"],
        "checks": ["rules"],
        "en": {
            "name": "Rules agent",
            "job": "Reads the ad for payment asks, pressure and claims that do not fit the record.",
            "tools": ["Rules table", "Ad claims vs the record", "Vexcel aerial date"],
            "never": ["Guesses: a rule fires or it does not", "Calls a named person a scammer"],
        },
        "es": {
            "name": "Agente de reglas",
            "job": "Busca en el anuncio pagos, presión y datos que no encajan con el registro.",
            "tools": ["Tabla de reglas", "Anuncio frente al registro", "Fecha aérea de Vexcel"],
            "never": [
                "Adivina: una regla se cumple o no",
                "Llama estafador a una persona con nombre",
            ],
        },
    },
    {
        "id": "record",
        "team": "scam_check",
        "model": "Claude Haiku",
        "kinds": ["record", "rent", "for_sale"],
        "checks": ["record", "forsale"],
        "en": {
            "name": "Record agent",
            "job": "Finds the building on CoStar's record: office, manager, website and rents.",
            "tools": ["CoStar record", "Floor-plan rents", "For-sale listings"],
            "never": ["Copies a raw record row into a note", "Guesses when the record is silent"],
        },
        "es": {
            "name": "Agente del registro",
            "job": "Busca el edificio en el registro de CoStar: oficina, gestor, web y rentas.",
            "tools": ["Registro de CoStar", "Rentas por plano", "Anuncios de venta"],
            "never": [
                "Copia una fila del registro en una nota",
                "Adivina cuando el registro no dice nada",
            ],
        },
    },
    {
        "id": "phone_office",
        "team": "scam_check",
        "model": "Claude Haiku",
        "kinds": ["phone", "office-and-licence"],
        "checks": ["phone"],
        "en": {
            "name": "Phone and office agent",
            "job": "Checks the ad's phone against the leasing office on record. Yes or no only.",
            "tools": ["CoStar record", "Keyed phone match"],
            "never": ["Shows or stores phone digits", "Names a person"],
        },
        "es": {
            "name": "Agente de teléfono y oficina",
            "job": "Compara el teléfono del anuncio con la oficina del registro. Solo sí o no.",
            "tools": ["Registro de CoStar", "Comparación de teléfono con clave"],
            "never": ["Muestra o guarda dígitos de teléfono", "Nombra a una persona"],
        },
    },
    {
        "id": "owner_licence",
        "team": "scam_check",
        "model": "Claude Haiku",
        "kinds": ["owner", "license", "ask_license"],
        "checks": ["owner"],
        "en": {
            "name": "Owner and licence agent",
            "job": "Looks up the county's owner of record and the licence the ad names.",
            "tools": ["County owner of record", "TREC licence lookup"],
            "never": ["Names a person in its note", "Keeps a licence number"],
        },
        "es": {
            "name": "Agente de propietario y licencia",
            "job": "Busca el propietario registrado en el condado y la licencia del anuncio.",
            "tools": ["Propietario registrado en el condado", "Consulta de licencia TREC"],
            "never": ["Nombra a una persona en su nota", "Guarda un número de licencia"],
        },
    },
    {
        "id": "photo",
        "team": "scam_check",
        "model": "Claude Haiku",
        "kinds": ["locate", "place", "reply"],
        "checks": ["photos"],
        "en": {
            "name": "Photo agent",
            "job": "Places the ad's photos in the building's 3D scan, and says which it could not.",
            "tools": ["Matterport scan", "Photo match"],
            "never": ["Sends a photo to an outside model", "Places a photo it cannot match"],
        },
        "es": {
            "name": "Agente de fotos",
            "job": "Ubica las fotos del anuncio en el escaneo 3D del edificio, y dice cuáles no.",
            "tools": ["Escaneo de Matterport", "Comparación de fotos"],
            "never": [
                "Envía una foto a un modelo externo",
                "Ubica una foto que no puede comparar",
            ],
        },
    },
    {
        "id": "web",
        "team": "scam_check",
        "model": "Claude Haiku",
        "kinds": ["web"],
        "checks": [],
        "en": {
            "name": "Web agent",
            "job": "Checks the building's own site, the ad's link and other listings on the web.",
            "tools": ["Bright Data", "Apify", "Browser Use"],
            "never": ["Opens a page behind a login", "Scrapes Facebook Marketplace"],
            "availability": "Available when the web checks are on",
        },
        "es": {
            "name": "Agente web",
            "job": "Revisa la web del edificio, el enlace del anuncio y otros anuncios en la red.",
            "tools": ["Bright Data", "Apify", "Browser Use"],
            "never": ["Abre una página con inicio de sesión", "Extrae Facebook Marketplace"],
            "availability": "Disponible cuando las comprobaciones web están activas",
        },
    },
    {
        "id": "finder",
        "team": "listing_help",
        "model": "Claude Haiku",
        "kinds": ["search"],
        "checks": [],
        "en": {
            "name": "Finder",
            "job": "Searches CoStar's record for safer homes that fit the budget.",
            "tools": ["CoStar record search", "Apartments.com hand-off"],
            "never": ["Lists a home that is not on the record"],
        },
        "es": {
            "name": "Buscador",
            "job": "Busca en el registro de CoStar casas más seguras dentro del presupuesto.",
            "tools": ["Búsqueda en el registro de CoStar", "Paso a Apartments.com"],
            "never": ["Muestra una casa que no está en el registro"],
        },
    },
    {
        "id": "tour_prep",
        "team": "listing_help",
        "model": "Claude Haiku",
        "kinds": ["walk"],
        "checks": [],
        "en": {
            "name": "Tour prep",
            "job": "Plans the walk through the 3D scan and what to ask on a tour.",
            "tools": ["Matterport scan", "Case notes"],
            "never": ["Changes a fact, a stop or a result"],
        },
        "es": {
            "name": "Preparación de visita",
            "job": "Planea el recorrido por el escaneo 3D y qué preguntar en una visita.",
            "tools": ["Escaneo de Matterport", "Notas del caso"],
            "never": ["Cambia un dato, una parada o un resultado"],
        },
    },
    {
        "id": "decider",
        "team": "decider",
        "model": "code",
        "kinds": ["report"],
        "checks": [],
        "en": {
            "name": "Decider",
            "job": "Works out the verdict from the evidence. The only one that sets the verdict.",
            "tools": ["decide() in code", "Evidence from every desk", "Report pack"],
            "never": ["Uses a language model", "Calls a home safe without proof"],
        },
        "es": {
            "name": "Decisor",
            "job": "Calcula el resultado a partir de las pruebas. El único que lo fija.",
            "tools": ["decide() en código", "Pruebas de cada puesto", "Informe"],
            "never": ["Usa un modelo de lenguaje", "Da una casa por segura sin pruebas"],
        },
    },
]


def cards(lang: str = "en") -> list[AgentCard]:
    """Every agent's card in floor order, in `lang` (English for a language we do not have)."""
    use: Lang = "es" if lang == "es" else "en"
    return [
        AgentCard(
            id=c["id"],
            team=c["team"],
            model=c["model"],
            kinds=list(c["kinds"]),
            checks=list(c["checks"]),
            **c[use],
        )
        for c in _CARDS
    ]


def card_for(kind: str, lang: str = "en") -> AgentCard | None:
    """The card a sub-agent name or a timeline step kind belongs to."""
    return next((c for c in cards(lang) if kind in c.kinds), None)


def roster(lang: str = "en") -> Roster:
    use: Lang = "es" if lang == "es" else "en"
    return Roster(
        lang=use,
        teams=[
            TeamInfo(id=t, name=_TEAMS[t][use][0], about=_TEAMS[t][use][1]) for t in TEAM_ORDER
        ],
        agents=cards(use),
    )


def web_copy() -> dict:
    """Both languages, as the web app ships them for the front end that has no API."""
    return {lang: json.loads(roster(lang).model_dump_json()) for lang in ("en", "es")}


if __name__ == "__main__":
    print(json.dumps(web_copy(), ensure_ascii=False, indent=2))
