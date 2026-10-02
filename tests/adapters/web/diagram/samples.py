from archimaid.adapters.web.diagram.model import (
    DiagramFlow,
    DiagramFunction,
    DiagramModel,
    DiagramNeighbour,
)


def flow(data_type, usage_mode=None, explanation=None):
    return DiagramFlow(data_type, usage_mode, explanation)


def neighbour(name, *flows):
    return DiagramNeighbour(name, tuple(flows))


# The data of the approved prototype renders (docs/superpowers/specs/assets/diagram/).
FULL = DiagramModel(
    application="Billing",
    functions=(
        DiagramFunction("Create invoice", "Accountant"),
        DiagramFunction("Send payment reminder", "Accountant"),
        DiagramFunction("Approve refund", "Finance manager"),
        DiagramFunction("Export ledger", "Auditor"),
        DiagramFunction("Archive documents", None),
    ),
    targets=(
        neighbour(
            "General Ledger",
            flow("Invoice", "Source", "posted nightly"),
            flow("Payment", "Source"),
        ),
        neighbour("Data Warehouse", flow("Invoice", "Source")),
        neighbour("Tax Authority Reporting Gateway Service", flow("VAT return", "Proxy")),
    ),
    sources=(
        neighbour("CRM", flow("Customer", "Source")),
        neighbour("Payment Gateway", flow("Transaction", "Source"), flow("Chargeback", "Source")),
        neighbour("ERP", flow("Price list", "Source"), flow("Product catalogue", "Source")),
        neighbour("General Ledger", flow("Exchange rates", "Source")),
    ),
    self_flows=1,
)

SMALL = DiagramModel(
    application="Notifier",
    functions=(DiagramFunction("Send email"), DiagramFunction("Send SMS")),
    targets=(neighbour("Mail server", flow("Message")),),
)

EMPTY = DiagramModel(application="Lonely app")

HOSTILE = DiagramModel(
    application='Evil <script>alert(1)</script> & "co"\x00',
    functions=(DiagramFunction("fn <b>bold</b>\x01", "P\"1'"),),
    targets=(neighbour("T&T <x>", flow("a<b>&c", "m", "e")),),
)
