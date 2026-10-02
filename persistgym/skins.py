"""Surface stories ("skins"). A skin supplies nouns only; the task structure is identical.

All agent-facing sentences are built from the fixed frames in `render.py`, so the oracle and
the audits can parse them. Entity names are upper-case single words; they are reserved per
template and never appear in log filler.

Entity names come in token-length classes (tokens of " NAME" in the project tokenizer). The
fact-withheld control replaces the target's bindings with bindings of equal token length about
another entity of the same class (PREREG D39), so every class holds at least
`MIN_TOKEN_CLASS` names: the target, up to 4 distractors and the stand-in. Generator 0.3.0
replaced 16 names that sat in smaller classes (a test checks the minimum).
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_TOKEN_CLASS = 6
"""Smallest number of a skin's entity names that share a token length: the target, up to 4
distractors (`GeneratorConfig.n_distractors` <= 4) and the withheld-control stand-in."""


@dataclass(frozen=True)
class Skin:
    name: str
    facility: str
    sites: tuple[str, ...]
    kind: str  # entity kind, lower case, one word
    entities: tuple[str, ...]
    quantity: str  # the target quantity, e.g. "loading bay"
    components: tuple[str, str, str]  # base, offset, shift (clue names)
    sources: tuple[str, str, str]  # record sources for clue 0/1/2 (observed uses sources[0])
    need_verb: str
    route_noun: str
    route_tags: tuple[str, ...]
    sensor_metrics: tuple[tuple[str, str], ...]  # (metric, unit); readings are 4-digit
    broadcast_senders: tuple[str, ...]
    services: tuple[str, ...]  # log filler service names


SKINS: dict[str, Skin] = {
    "warehouse": Skin(
        name="warehouse",
        facility="dispatch console",
        sites=("the Northgate distribution centre", "the Harbourside fulfilment hub",
               "the Ridgeway cross-dock"),
        kind="shipment",
        entities=("ORION", "VEGA", "RIGEL", "ALTAIR", "DENEB", "SIRIUS", "CAPELLA", "POLLUX",
                  "ANTARES", "BELLATRIX", "ALPHARD", "CANOPUS", "PROCYON", "SPICA",
                  "REGULUS", "MIRA", "MARKAB", "MIZAR", "ALCOR", "CASTOR", "ACHERNAR",
                  "HADAR", "SHAULA", "ELNATH", "ALHENA", "MENKAR", "NUNKI", "SABIK"),
        quantity="loading bay",
        components=("base bay", "priority offset", "lane shift"),
        sources=("Dispatch memo", "Priority desk note", "Yard notice"),
        need_verb="assign",
        route_noun="Ticket",
        route_tags=("billing", "customs", "inventory", "returns", "carrier", "packaging"),
        sensor_metrics=(("conveyor load", "kg"), ("dock pressure", "Pa"),
                        ("pallet weight", "kg"), ("belt speed", "mm/s")),
        broadcast_senders=("shift lead", "safety office", "yard control"),
        services=("wms-api", "scanner-gw", "conveyor-ctl", "label-svc", "route-planner",
                  "inv-sync", "auth-svc", "metrics-agent"),
    ),
    "biobank": Skin(
        name="biobank",
        facility="sample-tracking console",
        # No site may contain an entity name of its skin ("LINDEN" is an entity; a test checks).
        sites=("the Eastfield biobank", "the Calder clinical lab", "the Moorgate core facility"),
        kind="sample",
        entities=("ALDER", "BIRCH", "CEDAR", "ELM", "HAZEL", "HOLLY", "JUNIPER", "LARCH",
                  "MAPLE", "OAK", "PINE", "ROWAN", "SPRUCE", "WILLOW", "YEW", "ASPEN",
                  "BEECH", "CYPRESS", "WALNUT", "LAUREL", "LINDEN", "POPLAR", "HICKORY",
                  "SYCAMORE", "TAMARACK", "HEMLOCK", "CHERRY", "ACACIA"),
        quantity="freezer slot",
        components=("rack slot", "shelf offset", "overflow shift"),
        sources=("Intake memo", "Storage desk note", "Freezer notice"),
        need_verb="store",
        route_noun="Request",
        route_tags=("sequencing", "imaging", "assay", "billing", "shipping", "consent"),
        sensor_metrics=(("compressor current", "mA"), ("door cycle count", "cycles"),
                        ("LN2 level", "mm"), ("fan speed", "rpm")),
        broadcast_senders=("lab manager", "biosafety office", "facilities"),
        services=("lims-api", "barcode-gw", "freezer-mon", "label-svc", "sched-svc",
                  "inv-sync", "auth-svc", "metrics-agent"),
    ),
    "datacenter": Skin(
        name="datacenter",
        facility="hardware-ops console",
        sites=("the Westbrook data hall", "the Kestrel colocation site", "the Fenwick edge site"),
        kind="server",
        entities=("ATLAS", "BOREAS", "CALYPSO", "DAPHNE", "DIONE", "GAIA", "HELIOS", "IRIS",
                  "JANUS", "KRONOS", "LETO", "METIS", "NYX", "OCEANUS", "PALLAS", "RHEA",
                  "SELENE", "TETHYS", "THEIA", "URANIA", "ZEPHYR", "PHOEBE", "HYPERION",
                  "CRIUS", "COEUS", "THEMIS", "EUTERPE", "ASTRAEA"),
        quantity="rack position",
        components=("row base", "cage offset", "power shift"),
        sources=("Install memo", "Capacity desk note", "Power notice"),
        need_verb="mount",
        route_noun="Ticket",
        route_tags=("network", "storage", "cooling", "power", "security", "procurement"),
        sensor_metrics=(("inlet airflow", "cfm"), ("PDU draw", "W"), ("fan speed", "rpm"),
                        ("chassis count", "units")),
        broadcast_senders=("site lead", "change board", "NOC"),
        services=("dcim-api", "ipmi-gw", "pdu-ctl", "asset-svc", "netbox-sync", "auth-svc",
                  "metrics-agent", "cron"),
    ),
    "archive": Skin(
        name="archive",
        facility="records-retrieval console",
        sites=("the County records archive", "the Harlow university archive",
               "the Marsh library annex"),
        kind="box",
        entities=("THAMES", "DANUBE", "GANGES", "INDUS", "JORDAN", "LOIRE", "MEKONG",
                  "NIGER", "ORINOCO", "RHINE", "SEVERN", "TAGUS", "TIBER", "VOLGA", "YUKON",
                  "MERSEY", "ELBE", "ODER", "SHANNON", "TRENT", "CONGO", "DOURO", "EBRO",
                  "TIGRIS", "OHIO", "PLATTE", "RHONE", "SEINE"),
        quantity="shelf number",
        components=("aisle base", "bay offset", "annex shift"),
        sources=("Accession memo", "Reading-room note", "Stacks notice"),
        need_verb="shelve",
        route_noun="Request",
        route_tags=("conservation", "digitising", "loans", "reference", "copyright", "billing"),
        sensor_metrics=(("air exchange", "l/min"), ("lux exposure", "lux"),
                        ("CO2 reading", "ppm"), ("dust count", "particles")),
        broadcast_senders=("head archivist", "conservation office", "facilities"),
        services=("catalog-api", "scan-gw", "hvac-ctl", "label-svc", "search-idx", "auth-svc",
                  "metrics-agent", "cron"),
    ),
    "depot": Skin(
        name="depot",
        facility="fleet-depot console",
        sites=("the Southmere bus depot", "the Castlegate fleet yard", "the Brookside garage"),
        kind="vehicle",
        entities=("ALBATROSS", "BITTERN", "THRUSH", "DUNLIN", "EGRET", "FALCON",
                  "GANNET", "HERON", "IBIS", "KESTREL", "LAPWING", "MERLIN", "NIGHTJAR",
                  "LINNET", "PETREL", "QUAIL", "RAVEN", "GREBE", "TERN", "WAGTAIL",
                  "WREN", "SWIFT", "PLOVER", "CURLEW", "BUNTING", "PUFFIN", "SKYLARK",
                  "STARLING"),
        quantity="parking stall",
        components=("lot base", "charger offset", "rota shift"),
        sources=("Fleet memo", "Charging desk note", "Rota notice"),
        need_verb="park",
        route_noun="Work order",
        route_tags=("brakes", "tyres", "electrics", "bodywork", "cleaning", "telematics"),
        sensor_metrics=(("battery voltage", "mV"), ("charger current", "mA"),
                        ("tyre pressure", "hPa"), ("odometer delta", "m")),
        broadcast_senders=("depot manager", "safety office", "control room"),
        services=("fleet-api", "telematics-gw", "charger-ctl", "rota-svc", "parts-sync",
                  "auth-svc", "metrics-agent", "cron"),
    ),
}


def get_skin(name: str) -> Skin:
    try:
        return SKINS[name]
    except KeyError as e:
        raise ValueError(f"unknown skin {name!r}; known: {sorted(SKINS)}") from e
