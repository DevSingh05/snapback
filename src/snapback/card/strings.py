"""Every word a renter reads on a card, and every reason a verdict gives.

Code refers to these by key and never writes prose of its own, so a language model cannot put
words on a card and a reviewer can read the product's whole wording in this one file.

Conventions (tests/test_card_rows.py enforces them):

- No entry contains "safe", "verified" or "scam". About a person we say what was or was not
  shown, never what they are.
- Tone is never carried by colour alone. A red-flag line ends with "Red flag.", a `not_shown`
  line starts with "NOT SHOWN." or "Not confirmed." and a `not_checked` line starts with
  "Not checked".
- A rule that fires is worded under `rule.<rule_id>`. A rule id with no entry of its own falls
  back to `rule_category.<category>`, so a new rule can never put raw text on a card.
"""

DEFAULT_LANG = "en"

EN: dict[str, str] = {
    # --- line labels -----------------------------------------------------------------------
    "label.real": "Real",
    "label.here_now": "Here now",
    "label.allowed": "Allowed to rent it",
    "label.payment_ask": "Payment ask",
    "label.data_ask": "Data ask",
    "label.pressure": "Pressure",
    "label.rent_vs_record": "Rent vs record",
    "label.seen_before": "Seen before",
    "label.for_sale": "For sale",
    "label.recently_rented": "Rental history",
    "label.contact": "Contact on record",
    "label.link": "Link",
    "label.unit": "Unit on record",
    # --- PLACE: were the photos taken here? ------------------------------------------------
    "place.located_plan": (
        "Taken in this building, in the {floor_plan} floor plan ({located} of {total} photos)."
    ),
    "place.located": "Taken in this building ({located} of {total} photos).",
    "place.elsewhere": "Taken in a different building ({elsewhere} of {total} photos). Red flag.",
    "place.not_located": "NOT SHOWN. These photos could not be placed in this building's 3D scan.",
    "place.not_indexed": "Not checked (we have no 3D scan of this building).",
    "place.not_indexed_yet": "Not checked (this building's scan is not indexed yet).",
    "place.no_photos": "Not checked (no listing photos were sent).",
    "place.seen_before_dated": "A listing photo also appeared in another check on {date}.",
    "place.seen_before": "A listing photo also appeared in another check.",
    # For sale is a red flag, never proof: it holds a case and cannot set DON'T PAY by itself.
    # A warning, never a red flag, and never "not for rent" (red team H5, Sat 03:25). We do
    # not know whether a home is leased; the record says it is for sale, and so do we.
    "place.for_sale": (
        "Listed for sale on {site} by {brokerage} since {date}. Homes for sale are sometimes "
        "also offered for lease, so confirm with that brokerage before you pay."
    ),
    "place.for_sale_no_date": (
        "Listed for sale on {site} by {brokerage}. Homes for sale are sometimes also offered "
        "for lease, so confirm with that brokerage before you pay."
    ),
    "place.for_sale_no_brokerage": (
        "Listed for sale on {site} since {date}. Homes for sale are sometimes also offered "
        "for lease, so confirm with the listing brokerage before you pay."
    ),
    "place.for_sale_bare": (
        "Listed for sale on {site}. Homes for sale are sometimes also offered for lease, so "
        "confirm with the listing brokerage before you pay."
    ),
    # Lease status is something we do not know and never claim (ruling, Sat 01:20). This is
    # an information line: it carries no flag and holds no case by itself.
    "place.recently_rented": (
        "Not confirmed. The record shows it was rented recently. "
        "Ask the manager on record if it's still available."
    ),
    "place.recently_rented_dated": (
        "Not confirmed. The record shows it was rented on {date}. "
        "Ask the manager on record if it's still available."
    ),
    # --- PERSON: is someone there now, and may they rent it? -------------------------------
    "here_now.proven_plan": (
        "Someone with access to a {floor_plan} unit here sent these just now "
        "({matched} of {total} spots, code read, {time})."
    ),
    "here_now.proven": (
        "Someone with access to a unit here sent these just now "
        "({matched} of {total} spots, code read, {time})."
    ),
    "here_now.proven_bare": "Someone with access to a unit here proved it just now.",
    "here_now.waiting": "No reply yet. An honest landlord may need time.",
    "here_now.retry": "The reply photo could not be accepted. Ask for a new photo at a new spot.",
    # A reply came, could not be accepted, and nothing more will be asked (A14).
    "here_now.no_retry_left": (
        "We could not confirm they are there. Call the office on record yourself."
    ),
    # A14: a reply came. What it showed, and what nothing has checked yet.
    "here_now.code_only": (
        "Not confirmed. The reply shows the code we asked for, but nothing has checked "
        "that it was taken at the spot."
    ),
    "here_now.code_missing": (
        "The reply did not show the code we asked for. Ask for a new photo at a new spot."
    ),
    "here_now.not_requested": "Not checked (no one has been asked to prove they are inside yet).",
    "here_now.forged_copy": "The reply is a copy of listing photo {n}. Red flag.",
    "here_now.forged_copy_unknown": "The reply is a copy of one of the listing photos. Red flag.",
    "here_now.forged": "The reply was not a fresh photo taken in the unit. Red flag.",
    "here_now.seen_before_dated": "A reply photo also appeared in another check on {date}.",
    "here_now.seen_before": "A reply photo also appeared in another check.",
    "allowed.not_shown": "NOT SHOWN. Being inside does not mean they may rent it.",
    # A match never lifts this line: anyone can type a company's public name.
    "allowed.call_manager": (
        "Not confirmed. Call {manager} on a number you look up yourself before you pay."
    ),
    "allowed.call_manager_unnamed": (
        "Not confirmed. Call the manager on record on a number you look up yourself before you pay."
    ),
    # A name that is not the one on record is never a red flag by itself (ruling, Sat 01:20):
    # the manager, the leasing office and a listing brokerage may all market a home.
    "allowed.call_office": "Not confirmed. Call the office on record yourself.",
    # Contact on record. The phone number itself and the record's web address are never shown.
    # A match is a supporting line only. It never counts as matching the record by itself.
    "contact.phone_match": (
        "The phone matches the leasing office on record. Call it yourself to confirm."
    ),
    # H1: the name matches the record and there was no phone to compare with the office's.
    "contact.phone_unchecked": (
        "Not checked (no phone number in the listing could be compared with the leasing "
        "office on record)."
    ),
    # Not a red flag (ruling, Sat 02:10, #121): agents and locators often post with their own
    # number. The line is Not confirmed, and it says who to call.
    "contact.phone_mismatch": (
        "Not confirmed. This number is not the leasing office's on record. "
        "Agents often use their own, so check it with the office."
    ),
    "contact.phone_mismatch_unnamed": (
        "Not confirmed. This number is not the leasing office's on record. "
        "Agents often use their own. Call the office on record yourself to confirm."
    ),
    "contact.lookalike_link": (
        "A link in the listing imitates this building's website but is not it. Red flag."
    ),
    # --- PRICE: what are they asking for, and does the rent fit? ---------------------------
    "payment.none": "No risky payment ask found in the text you sent.",
    # One entry per red-flag rule in agent/rules/table.py, keyed by its rule id.
    "rule.payment.zelle_before_viewing": "Zelle before a viewing. Red flag.",
    "rule.payment.wire_before_viewing": "Wire transfer before a viewing. Red flag.",
    "rule.payment.p2p_app_before_viewing": "Payment by app before a viewing. Red flag.",
    "rule.payment.gift_card": "Gift cards as payment. Red flag.",
    "rule.payment.crypto": "Crypto as payment. Red flag.",
    "rule.payment.overpayment_refund": (
        "More money than is owed, with the difference to be sent back. Red flag."
    ),
    "rule.fee.holding_deposit_before_viewing": (
        "A deposit or holding fee before a viewing. Red flag."
    ),
    "rule.fee.application_fee_before_viewing": (
        "An application fee sent to a person before a viewing. Red flag."
    ),
    "rule.data.ssn_before_viewing": "Social Security number before a viewing. Red flag.",
    "rule.data.bank_login": "Bank login details. Red flag.",
    "rule.data.id_before_viewing": "A photo of your ID before a viewing. Red flag.",
    "rule.pressure.cannot_show": "They say they cannot show the unit in person. Red flag.",
    "rule.link.payment_link": "A payment link sent by the poster. Red flag.",
    "rule_category.payment_method": (
        "A payment that cannot be taken back, asked for before a viewing. Red flag."
    ),
    "rule_category.fee_ask": "A fee to a person before a viewing. Red flag.",
    "rule_category.data_ask": "Personal or bank details asked for before a viewing. Red flag.",
    "rule_category.pressure": "Pressure to decide fast. Red flag.",
    "rule_category.link": "A payment or lease link sent by the poster. Red flag.",
    "rent.not_checked": "Not checked (our data has no rent for this building).",
    "rent.within_range": "In line with the rents on record for this building.",
    "rent.below_range": "Below the rents on record for this building. Ask why; discounts happen.",
    # "NN% under this building's lowest N bed": the comparison with the listing's own size.
    "rent.below_floor_plan": (
        "{percent}% under this building's lowest {plan} on record. Ask why; discounts happen."
    ),
    "rent.plan.studio": "studio",
    "rent.plan.beds": "{beds} bed",
    "rent.per_bed": "Not checked (priced per bed here, so the rent was not compared).",
    "unit.not_on_record": (
        "The record for this building lists no unit with that number. Ask the manager on record."
    ),
    "unit.beds_mismatch": (
        "The bedroom count in the listing does not match the record for this building. "
        "Ask the manager on record."
    ),
    # --- what no card ever checks, and the two lines under every card ----------------------
    "not_checked.id": "ID",
    "not_checked.lease": "lease",
    "not_checked.ownership": "ownership",
    "footer.two_rules": (
        "Two rules: never pay before a signed lease and a viewing; "
        "never pay by Zelle, wire or gift card."
    ),
    "footer.only_trust": (
        "Only trust a SNAPBACK result you asked for yourself. "
        "SNAPBACK never texts first or asks for money."
    ),
    # On every card made from a staged demo case (fixtures/demo), first in the footer.
    "footer.staged": (
        "Staged example. The SNAPBACK team wrote this listing to show the checks. "
        "It is not a real poster."
    ),
    # --- the challenge message the renter relays, and the agent's own trace lines ----------
    "challenge.text": (
        "Before you pay, ask them to send a photo of {spot} with the code {code} written on paper."
    ),
    "trace.checks.twin": "The building is in our data area and has a 3D twin.",
    "trace.checks.no_twin": "We have no 3D scan of this building, so only the text can be checked.",
    "trace.checks.short_term": (
        "This is a short-term stay listing, which this check does not cover."
    ),
    "trace.checks.commercial": "This is a commercial listing, which this check does not cover.",
    "trace.tool.locate": "Placing {count} listing photos in the twin.",
    "trace.floor_plan.best": "{alias}: {best} inliers vs {next}.",
    "trace.floor_plan.only": "Only one floor plan is in the running.",
    "trace.floor_plan.unranked": "No photo was placed, so the first floor plan on record is used.",
    "trace.spot.draw": "Random draw from the top {count}.",
    "trace.spot.draw_skipped_one": (
        "Random draw from the top {count}; {skipped} skipped because it overlaps a listing photo."
    ),
    "trace.spot.draw_skipped_many": (
        "Random draw from the top {count}; {skipped} spots skipped because they overlap "
        "listing photos."
    ),
    "trace.hitl.waiting": (
        "Waiting for the renter to approve the message. Nothing is sent until then."
    ),
    "trace.hitl.send": "The renter approved the challenge text.",
    "trace.reply.waiting": (
        "The message is with the renter to pass on. Waiting for the poster's reply photo."
    ),
    "trace.tool.reply": "Checked the reply photo for the code and against the listing photos.",
    "trace.hitl.edit": "The renter edited the challenge text and approved it.",
    "trace.hitl.cancel": "The renter chose not to send a challenge.",
    "trace.retry.accept_both": "Both spots matched with the code read and no recapture flag.",
    "trace.retry.accept": (
        "{matched} of {total} spots matched with the code read and no recapture flag."
    ),
    "trace.retry.forged": "The reply failed the check, so there is nothing to retry.",
    "trace.retry.again": "The reply could not be accepted, so we ask again at a new spot.",
    "trace.retry.late": "The reply came too late to count, so we ask once more at a new spot.",
    "trace.reply.late": (
        "The reply came after the time limit. It was compared with the listing photos and "
        "not counted."
    ),
    "trace.retry.code_only": (
        "The reply shows the code. Whether it was taken at the spot cannot be checked yet, "
        "so it stays not confirmed."
    ),
    "trace.retry.stop": (
        "The reply could not be accepted and no retry is left, so the result stays on hold."
    ),
    "trace.error.bad_pick": (
        "The model answered with something that was not on the list, so the default was used."
    ),
    "trace.error.model_failed": "The model could not be used, so the default was used.",
    "trace.intake.injection": (
        "The listing has text written for an AI system. It was ignored, and the checks go on."
    ),
    "trace.intake.truncated": (
        "The text you sent was very long. Only the first 20,000 characters were read. "
        "The rest was not checked."
    ),
    # --- reasons a verdict gives (Verdict.reasons, Evidence.forgery_reason) ----------------
    "reason.forged": "The proof-of-presence reply was not a fresh photo taken in the unit.",
    "reason.forged_copy": "The reply is a copy of listing photo {n}.",
    "reason.forged_copy_unknown": "The reply is a copy of one of the listing photos.",
    "reason.photo_elsewhere": "At least one listing photo was taken in a different property.",
    "reason.price_flag": "The rent is far below comparable units.",
    "reason.payment_flag": "Payment was requested before any viewing.",
    "reason.rule_flag": "Something in the text you sent is a red flag.",
    "reason.for_sale": (
        "This home is listed for sale. Confirm with the listing brokerage that it is also "
        "offered for lease."
    ),
    "reason.phone_not_confirmed": (
        "The contact in the listing was not shown to be the leasing office on record."
    ),
    "reason.phone_flag": "The phone in the listing is not the leasing office on record.",
    "reason.lookalike_link": "A link in the listing imitates the building's website.",
    "reason.unit_flag": "The unit in the listing does not fit the record for this building.",
    "reason.not_indexed": (
        "This property has no 3D twin in our index, so the photos could not be checked."
    ),
    "reason.not_located": "The photos could not be located in this property's 3D twin.",
    "reason.located": "The photos were located in this property.",
    "reason.authority_matches": "The poster matches the contact on the property record.",
    "reason.authority_unknown": "We could not confirm who is allowed to rent this unit.",
    "reason.presence_proven": "A fresh photo proved someone was inside the unit.",
    "reason.presence_proven_not_authority": (
        "A fresh photo proved someone was inside the unit, which is not authority."
    ),
    "reason.presence_missing": "Nobody has proved they are inside the unit yet.",
    # --- the card's own words: row titles, tone and state labels, the header -------------
    "row.place": "PLACE",
    "row.person": "PERSON",
    "row.price": "PRICE",
    # LOCKED wording (decisions Fri 22:40, XO review of #59). Five row states: Matches,
    # Doesn't match, Not confirmed, Warning, Not checked. Three headlines. Do not reword.
    # A row state is chosen by `tone_word`: by the line's tone, and for two tones by its row.
    "tone.ok": "Matches",
    "tone.hold": "Warning",
    "tone.hold.person": "Not confirmed",  # no reply yet is not a warning about anyone
    "tone.red_flag": "Doesn't match",
    "tone.red_flag.price": "Warning",  # a risky ask is a warning, not a mismatch
    "tone.not_shown": "Not confirmed",
    "tone.not_checked": "Not checked",
    "state.hold": "Hold off for now",
    "state.dont_pay": "Don't pay. Something here doesn't match.",
    "state.unverified": "Could not place these photos",
    "state.verified": "Checks passed. Still follow the two rules.",
    "card.case": "Case {case_id}",
    "card.checked": "Checked {time}",
    "card.expires": "Expires {time}",
    "card.not_checked": "Not checked by SNAPBACK: {items}",
    "card.verify": "Check this card yourself:",
    "card.source.fixture": "FIXTURE",
    "card.source.live": "LIVE",
}

# Spanish, for Houston. Same keys and the same blanks as EN; tests hold it to both.
# Banned here: estafa, seguro, verificado. A red-flag line ends "Señal de alerta.", a
# not-shown line starts "NO DEMOSTRADO." or "Sin confirmar.", a not-checked line starts
# "No comprobado".
ES: dict[str, str] = {
    "label.real": "Real",
    "label.here_now": "Aquí ahora",
    "label.allowed": "Con permiso para alquilarlo",
    "label.payment_ask": "Pago que piden",
    "label.data_ask": "Datos que piden",
    "label.pressure": "Presión",
    "label.rent_vs_record": "Renta frente al registro",
    "label.seen_before": "Visto antes",
    "label.for_sale": "En venta",
    "label.recently_rented": "Historial de alquiler",
    "label.contact": "Contacto en el registro",
    "label.link": "Enlace",
    "label.unit": "Unidad en el registro",
    "place.located_plan": (
        "Tomadas en este edificio, en el plano de {floor_plan} ({located} de {total} fotos)."
    ),
    "place.located": "Tomadas en este edificio ({located} de {total} fotos).",
    "place.elsewhere": "Tomadas en otro edificio ({elsewhere} de {total} fotos). Señal de alerta.",
    "place.not_located": (
        "NO DEMOSTRADO. Estas fotos no se pudieron ubicar en el escaneo 3D de este edificio."
    ),
    "place.not_indexed": "No comprobado (no tenemos un escaneo 3D de este edificio).",
    "place.not_indexed_yet": (
        "No comprobado (el escaneo de este edificio todavía no está indexado)."
    ),
    "place.no_photos": "No comprobado (no se enviaron fotos del anuncio).",
    "place.seen_before_dated": "Una foto del anuncio también apareció en otra revisión el {date}.",
    "place.seen_before": "Una foto del anuncio también apareció en otra revisión.",
    "place.for_sale": (
        "En venta en {site} por {brokerage} desde el {date}. Las viviendas en venta a veces "
        "también se ofrecen en alquiler, así que confírmelo con esa agencia antes de pagar."
    ),
    "place.for_sale_no_date": (
        "En venta en {site} por {brokerage}. Las viviendas en venta a veces también se "
        "ofrecen en alquiler, así que confírmelo con esa agencia antes de pagar."
    ),
    "place.for_sale_no_brokerage": (
        "En venta en {site} desde el {date}. Las viviendas en venta a veces también se "
        "ofrecen en alquiler, así que confírmelo con la agencia que la anuncia antes de pagar."
    ),
    "place.for_sale_bare": (
        "En venta en {site}. Las viviendas en venta a veces también se ofrecen en alquiler, "
        "así que confírmelo con la agencia que la anuncia antes de pagar."
    ),
    "place.recently_rented": (
        "Sin confirmar. El registro muestra que se alquiló hace poco. "
        "Pregunte al administrador que figura en el registro si sigue disponible."
    ),
    "place.recently_rented_dated": (
        "Sin confirmar. El registro muestra que se alquiló el {date}. "
        "Pregunte al administrador que figura en el registro si sigue disponible."
    ),
    "here_now.proven_plan": (
        "Alguien con acceso a una unidad de {floor_plan} aquí las envió ahora mismo "
        "({matched} de {total} puntos, código leído, {time})."
    ),
    "here_now.proven": (
        "Alguien con acceso a una unidad aquí las envió ahora mismo ({matched} de {total} "
        "puntos, código leído, {time})."
    ),
    "here_now.proven_bare": "Alguien con acceso a una unidad aquí lo demostró ahora mismo.",
    "here_now.waiting": "Aún sin respuesta. Un arrendador honesto puede necesitar tiempo.",
    "here_now.retry": "No se pudo aceptar la foto de respuesta. Pida una foto nueva en otro punto.",
    "here_now.no_retry_left": (
        "No pudimos confirmar que están allí. Llame usted mismo a la oficina que figura en "
        "el registro."
    ),
    "here_now.code_only": (
        "Sin confirmar. La respuesta muestra el código que pedimos, pero nada ha comprobado "
        "que se tomó en el punto indicado."
    ),
    "here_now.code_missing": (
        "La respuesta no mostró el código que pedimos. Pida una foto nueva en otro punto."
    ),
    "here_now.not_requested": (
        "No comprobado (aún no se ha pedido a nadie que demuestre que está dentro)."
    ),
    "here_now.forged_copy": (
        "La respuesta es una copia de la foto {n} del anuncio. Señal de alerta."
    ),
    "here_now.forged_copy_unknown": (
        "La respuesta es una copia de una de las fotos del anuncio. Señal de alerta."
    ),
    "here_now.forged": "La respuesta no era una foto nueva tomada en la unidad. Señal de alerta.",
    "here_now.seen_before_dated": (
        "Una foto de respuesta también apareció en otra revisión el {date}."
    ),
    "here_now.seen_before": "Una foto de respuesta también apareció en otra revisión.",
    "allowed.not_shown": "NO DEMOSTRADO. Estar dentro no significa que pueda alquilarlo.",
    "allowed.call_manager": (
        "Sin confirmar. Llame a {manager} a un número que usted mismo busque antes de pagar."
    ),
    "allowed.call_manager_unnamed": (
        "Sin confirmar. Llame al administrador que figura en el registro, a un número que "
        "usted mismo busque, antes de pagar."
    ),
    "allowed.call_office": (
        "Sin confirmar. Llame usted mismo a la oficina que figura en el registro."
    ),
    "contact.phone_match": (
        "El teléfono coincide con el de la oficina de alquiler que figura en el registro. "
        "Llame usted mismo para confirmarlo."
    ),
    "contact.phone_unchecked": (
        "No comprobado (ningún teléfono del anuncio se pudo comparar con el de la oficina de "
        "alquiler que figura en el registro)."
    ),
    "contact.phone_mismatch": (
        "Sin confirmar. Este número no es el de la oficina de alquiler que figura en el "
        "registro. Los agentes suelen usar el suyo, así que confírmelo con la oficina."
    ),
    "contact.phone_mismatch_unnamed": (
        "Sin confirmar. Este número no es el de la oficina de alquiler que figura en el "
        "registro. Los agentes suelen usar el suyo. Llame usted mismo a la oficina que figura "
        "en el registro para confirmarlo."
    ),
    "contact.lookalike_link": (
        "Un enlace del anuncio imita el sitio web de este edificio, pero no lo es. Señal de alerta."
    ),
    "payment.none": "No se encontró ningún pedido de pago riesgoso en el texto que envió.",
    "rule.payment.zelle_before_viewing": "Zelle antes de una visita. Señal de alerta.",
    "rule.payment.wire_before_viewing": (
        "Transferencia bancaria antes de una visita. Señal de alerta."
    ),
    "rule.payment.p2p_app_before_viewing": (
        "Pago por aplicación antes de una visita. Señal de alerta."
    ),
    "rule.payment.gift_card": "Tarjetas de regalo como pago. Señal de alerta.",
    "rule.payment.crypto": "Criptomonedas como pago. Señal de alerta.",
    "rule.payment.overpayment_refund": (
        "Más dinero del que se debe, con la diferencia por devolver. Señal de alerta."
    ),
    "rule.fee.holding_deposit_before_viewing": (
        "Un depósito o cargo de reserva antes de una visita. Señal de alerta."
    ),
    "rule.fee.application_fee_before_viewing": (
        "Un cargo de solicitud enviado a una persona antes de una visita. Señal de alerta."
    ),
    "rule.data.ssn_before_viewing": (
        "Número de SSN (Social Security) antes de una visita. Señal de alerta."
    ),
    "rule.data.bank_login": "Datos de acceso al banco. Señal de alerta.",
    "rule.data.id_before_viewing": (
        "Una foto de su identificación antes de una visita. Señal de alerta."
    ),
    "rule.pressure.cannot_show": (
        "Dicen que no pueden mostrar la unidad en persona. Señal de alerta."
    ),
    "rule.link.payment_link": (
        "Un enlace de pago enviado por quien publicó el anuncio. Señal de alerta."
    ),
    "rule_category.payment_method": (
        "Un pago que no se puede recuperar, pedido antes de una visita. Señal de alerta."
    ),
    "rule_category.fee_ask": "Un cargo a una persona antes de una visita. Señal de alerta.",
    "rule_category.data_ask": (
        "Datos personales o bancarios pedidos antes de una visita. Señal de alerta."
    ),
    "rule_category.pressure": "Presión para decidir rápido. Señal de alerta.",
    "rule_category.link": (
        "Un enlace de pago o de contrato enviado por quien publicó el anuncio. Señal de alerta."
    ),
    "rent.not_checked": "No comprobado (nuestros datos no tienen la renta de este edificio).",
    "rent.within_range": "Acorde con las rentas que figuran en el registro de este edificio.",
    "rent.below_range": (
        "Por debajo de las rentas que figuran en el registro de este edificio. Pregunte por "
        "qué; hay descuentos."
    ),
    "rent.below_floor_plan": (
        "{percent}% por debajo de la renta más baja que figura en el registro de este edificio "
        "para {plan}. Pregunte por qué; hay descuentos."
    ),
    "rent.plan.studio": "un estudio",
    "rent.plan.beds": "{beds} hab.",
    "rent.per_bed": "No comprobado (aquí se cobra por cama, así que la renta no se comparó).",
    "unit.not_on_record": (
        "El registro de este edificio no tiene ninguna unidad con ese número. "
        "Pregunte al administrador que figura en el registro."
    ),
    "unit.beds_mismatch": (
        "El número de habitaciones del anuncio no coincide con el registro de este edificio. "
        "Pregunte al administrador que figura en el registro."
    ),
    "not_checked.id": "identificación",
    "not_checked.lease": "contrato",
    "not_checked.ownership": "propiedad",
    "footer.two_rules": (
        "Dos reglas: nunca pague antes de firmar el contrato y visitar la unidad; nunca pague"
        " por Zelle, transferencia o tarjeta de regalo."
    ),
    "footer.only_trust": (
        "Confíe solo en un resultado de SNAPBACK que usted mismo pidió. SNAPBACK nunca "
        "escribe primero ni pide dinero."
    ),
    "footer.staged": (
        "Ejemplo preparado. El equipo de SNAPBACK escribió este anuncio para mostrar las "
        "revisiones. No es un anunciante real."
    ),
    "challenge.text": (
        "Antes de pagar, pídales que envíen una foto de {spot} con el código {code} escrito "
        "en papel."
    ),
    "trace.checks.twin": "El edificio está en nuestra zona de datos y tiene un gemelo 3D.",
    "trace.checks.no_twin": (
        "No tenemos un escaneo 3D de este edificio, así que solo se puede revisar el texto."
    ),
    "trace.checks.short_term": "Este es un anuncio de estancia corta, que esta revisión no cubre.",
    "trace.checks.commercial": "Este es un anuncio comercial, que esta revisión no cubre.",
    "trace.tool.locate": "Ubicando {count} fotos del anuncio en el gemelo.",
    "trace.floor_plan.best": "{alias}: {best} coincidencias frente a {next}.",
    "trace.floor_plan.only": "Solo hay un plano posible.",
    "trace.floor_plan.unranked": (
        "No se ubicó ninguna foto, así que se usa el primer plano del registro."
    ),
    "trace.spot.draw": "Sorteo al azar entre los {count} mejores.",
    "trace.spot.draw_skipped_one": (
        "Sorteo al azar entre los {count} mejores; se omitió {skipped} porque coincide con "
        "una foto del anuncio."
    ),
    "trace.spot.draw_skipped_many": (
        "Sorteo al azar entre los {count} mejores; se omitieron {skipped} puntos porque "
        "coinciden con fotos del anuncio."
    ),
    "trace.hitl.waiting": (
        "Esperando a que el inquilino apruebe el mensaje. No se envía nada hasta entonces."
    ),
    "trace.hitl.send": "El inquilino aprobó el texto del reto.",
    "trace.reply.waiting": (
        "El mensaje está con el inquilino para que lo pase. Esperando la foto de respuesta "
        "del anunciante."
    ),
    "trace.tool.reply": (
        "Se revisó la foto de respuesta: el código y su parecido con las fotos del anuncio."
    ),
    "trace.hitl.edit": "El inquilino editó el texto del reto y lo aprobó.",
    "trace.hitl.cancel": "El inquilino decidió no enviar un reto.",
    "trace.retry.accept_both": (
        "Los dos puntos coincidieron, con el código leído y sin aviso de recaptura."
    ),
    "trace.retry.accept": (
        "{matched} de {total} puntos coincidieron, con el código leído y sin aviso de recaptura."
    ),
    "trace.retry.forged": "La respuesta no pasó la revisión, así que no hay nada que reintentar.",
    "trace.retry.code_only": (
        "La respuesta muestra el código. Todavía no se puede comprobar si se tomó en el punto "
        "indicado, así que queda sin confirmar."
    ),
    "trace.retry.again": "No se pudo aceptar la respuesta, así que pedimos otra en un punto nuevo.",
    "trace.retry.late": (
        "La respuesta llegó demasiado tarde para contar, así que pedimos una más en un punto nuevo."
    ),
    "trace.reply.late": (
        "La respuesta llegó después del límite de tiempo. Se comparó con las fotos del "
        "anuncio y no se contó."
    ),
    "trace.retry.stop": (
        "No se pudo aceptar la respuesta y no quedan reintentos, así que el resultado queda "
        "en espera."
    ),
    "trace.error.bad_pick": (
        "El modelo respondió con algo que no estaba en la lista, así que se usó la opción por"
        " defecto."
    ),
    "trace.error.model_failed": "No se pudo usar el modelo, así que se usó la opción por defecto.",
    "trace.intake.injection": (
        "El anuncio tiene texto escrito para un sistema de IA. Se ignoró y las revisiones "
        "continúan."
    ),
    "trace.intake.truncated": (
        "El texto que enviaste era muy largo. Solo se leyeron los primeros 20,000 caracteres. "
        "El resto no se revisó."
    ),
    "reason.forged": (
        "La respuesta a la prueba de presencia no era una foto nueva tomada en la unidad."
    ),
    "reason.forged_copy": "La respuesta es una copia de la foto {n} del anuncio.",
    "reason.forged_copy_unknown": "La respuesta es una copia de una de las fotos del anuncio.",
    "reason.photo_elsewhere": "Al menos una foto del anuncio se tomó en otra propiedad.",
    "reason.price_flag": "La renta está muy por debajo de unidades comparables.",
    "reason.payment_flag": "Se pidió un pago antes de cualquier visita.",
    "reason.rule_flag": "Algo en el texto que envió es una señal de alerta.",
    "reason.for_sale": (
        "Esta vivienda está en venta. Confirme con la agencia que la anuncia que también se "
        "ofrece en alquiler."
    ),
    "reason.phone_not_confirmed": (
        "No se demostró que el contacto del anuncio sea la oficina de alquiler que figura en "
        "el registro."
    ),
    "reason.phone_flag": (
        "El teléfono del anuncio no es el de la oficina de alquiler que figura en el registro."
    ),
    "reason.lookalike_link": "Un enlace del anuncio imita el sitio web del edificio.",
    "reason.unit_flag": "La unidad del anuncio no encaja con el registro de este edificio.",
    "reason.not_indexed": (
        "Esta propiedad no tiene un gemelo 3D en nuestro índice, así que no se pudieron "
        "revisar las fotos."
    ),
    "reason.not_located": "Las fotos no se pudieron ubicar en el gemelo 3D de esta propiedad.",
    "reason.located": "Las fotos se ubicaron en esta propiedad.",
    "reason.authority_matches": (
        "Quien publicó el anuncio coincide con el contacto del registro de la propiedad."
    ),
    "reason.authority_unknown": "No pudimos confirmar quién puede alquilar esta unidad.",
    "reason.presence_proven": "Una foto nueva demostró que alguien estaba dentro de la unidad.",
    "reason.presence_proven_not_authority": (
        "Una foto nueva demostró que alguien estaba dentro de la unidad, lo cual no es "
        "autorización."
    ),
    "reason.presence_missing": "Nadie ha demostrado todavía que está dentro de la unidad.",
    "row.place": "LUGAR",
    "row.person": "PERSONA",
    "row.price": "PRECIO",
    # The locked English wording, in Spanish. Same keys, same rule for choosing a row state.
    "tone.ok": "Coincide",
    "tone.hold": "Advertencia",
    "tone.hold.person": "Sin confirmar",
    "tone.red_flag": "No coincide",
    "tone.red_flag.price": "Advertencia",
    "tone.not_shown": "Sin confirmar",
    "tone.not_checked": "No comprobado",
    "state.hold": "Espere por ahora",
    "state.dont_pay": "No pague. Algo aquí no coincide.",
    "state.unverified": "No se pudieron ubicar estas fotos",
    "state.verified": "Las revisiones pasaron. Siga igual las dos reglas.",
    "card.case": "Caso {case_id}",
    "card.checked": "Revisado {time}",
    "card.expires": "Vence {time}",
    "card.not_checked": "SNAPBACK no revisó: {items}",
    "card.verify": "Compruebe esta tarjeta usted mismo:",
    "card.source.fixture": "DATOS DE PRUEBA",
    "card.source.live": "EN VIVO",
}

TABLES: dict[str, dict[str, str]] = {DEFAULT_LANG: EN, "es": ES}


def _table(lang: str) -> dict[str, str]:
    return TABLES.get(lang, TABLES[DEFAULT_LANG])


def has(key: str, lang: str = DEFAULT_LANG) -> bool:
    return key in _table(lang)


def text(key: str, lang: str = DEFAULT_LANG, **values: object) -> str:
    """The wording for `key`, with `{placeholders}` filled in. A missing key is a bug: KeyError."""
    return _table(lang)[key].format(**values)


def tone_word(tone: str, row: str, lang: str = DEFAULT_LANG) -> str:
    """The locked word shown beside a card line: its row state.

    One word per tone, except where the row changes what the tone means. A red flag on the
    PRICE row is a risky ask ("Warning"); on PLACE or PERSON it is something that contradicts
    the listing ("Doesn't match"). A hold on the PERSON row is someone not heard from yet
    ("Not confirmed"); elsewhere it is something to ask about ("Warning"). `tone` and `row`
    are the values of `CardTone` and `CardRowKind`.
    """
    by_row = f"tone.{tone}.{row}"
    return text(by_row if has(by_row, lang) else f"tone.{tone}", lang)
