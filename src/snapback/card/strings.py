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
    # --- PLACE: were the photos taken here? ------------------------------------------------
    "place.located_plan": (
        "Taken in this building, in the {floor_plan} floor plan ({located} of {total} photos)."
    ),
    "place.located": "Taken in this building ({located} of {total} photos).",
    "place.elsewhere": "Taken in a different building ({elsewhere} of {total} photos). Red flag.",
    "place.not_located": "NOT SHOWN. These photos could not be placed in this building's 3D scan.",
    "place.not_indexed": "Not checked (we have no 3D scan of this building).",
    "place.no_photos": "Not checked (no listing photos were sent).",
    "place.seen_before_dated": "A listing photo also appeared in another check on {date}.",
    "place.seen_before": "A listing photo also appeared in another check.",
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
    "allowed.mismatch": (
        "The name they gave does not match the manager on record for this building. Red flag."
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
    "trace.hitl.edit": "The renter edited the challenge text and approved it.",
    "trace.hitl.cancel": "The renter chose not to send a challenge.",
    "trace.retry.accept_both": "Both spots matched with the code read and no recapture flag.",
    "trace.retry.accept": (
        "{matched} of {total} spots matched with the code read and no recapture flag."
    ),
    "trace.retry.forged": "The reply failed the check, so there is nothing to retry.",
    "trace.retry.again": "The reply could not be accepted, so we ask again at a new spot.",
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
    # --- reasons a verdict gives (Verdict.reasons, Evidence.forgery_reason) ----------------
    "reason.forged": "The proof-of-presence reply was not a fresh photo taken in the unit.",
    "reason.forged_copy": "The reply is a copy of listing photo {n}.",
    "reason.forged_copy_unknown": "The reply is a copy of one of the listing photos.",
    "reason.photo_elsewhere": "At least one listing photo was taken in a different property.",
    "reason.authority_mismatch": "The poster does not match the contact on the property record.",
    "reason.price_flag": "The rent is far below comparable units.",
    "reason.payment_flag": "Payment was requested before any viewing.",
    "reason.rule_flag": "Something in the text you sent is a red flag.",
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
    "tone.ok": "Held up",
    "tone.hold": "On hold",
    "tone.red_flag": "Red flag",
    "tone.not_shown": "Not shown",
    "tone.not_checked": "Not checked",
    "state.hold": "Hold",
    "state.dont_pay": "Don't pay · could not verify",
    "state.unverified": "Could not place these photos",
    "state.verified": "Checks held up",
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
    "place.located_plan": (
        "Tomadas en este edificio, en el plano de {floor_plan} ({located} de {total} fotos)."
    ),
    "place.located": "Tomadas en este edificio ({located} de {total} fotos).",
    "place.elsewhere": "Tomadas en otro edificio ({elsewhere} de {total} fotos). Señal de alerta.",
    "place.not_located": (
        "NO DEMOSTRADO. Estas fotos no se pudieron ubicar en el escaneo 3D de este edificio."
    ),
    "place.not_indexed": "No comprobado (no tenemos un escaneo 3D de este edificio).",
    "place.no_photos": "No comprobado (no se enviaron fotos del anuncio).",
    "place.seen_before_dated": "Una foto del anuncio también apareció en otra revisión el {date}.",
    "place.seen_before": "Una foto del anuncio también apareció en otra revisión.",
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
    "allowed.mismatch": (
        "El nombre que dieron no coincide con el administrador que figura en el registro de "
        "este edificio. Señal de alerta."
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
    "trace.hitl.edit": "El inquilino editó el texto del reto y lo aprobó.",
    "trace.hitl.cancel": "El inquilino decidió no enviar un reto.",
    "trace.retry.accept_both": (
        "Los dos puntos coincidieron, con el código leído y sin aviso de recaptura."
    ),
    "trace.retry.accept": (
        "{matched} de {total} puntos coincidieron, con el código leído y sin aviso de recaptura."
    ),
    "trace.retry.forged": "La respuesta no pasó la revisión, así que no hay nada que reintentar.",
    "trace.retry.again": "No se pudo aceptar la respuesta, así que pedimos otra en un punto nuevo.",
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
    "reason.forged": (
        "La respuesta a la prueba de presencia no era una foto nueva tomada en la unidad."
    ),
    "reason.forged_copy": "La respuesta es una copia de la foto {n} del anuncio.",
    "reason.forged_copy_unknown": "La respuesta es una copia de una de las fotos del anuncio.",
    "reason.photo_elsewhere": "Al menos una foto del anuncio se tomó en otra propiedad.",
    "reason.authority_mismatch": (
        "Quien publicó el anuncio no coincide con el contacto del registro de la propiedad."
    ),
    "reason.price_flag": "La renta está muy por debajo de unidades comparables.",
    "reason.payment_flag": "Se pidió un pago antes de cualquier visita.",
    "reason.rule_flag": "Algo en el texto que envió es una señal de alerta.",
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
    "tone.ok": "Se sostuvo",
    "tone.hold": "En espera",
    "tone.red_flag": "Señal de alerta",
    "tone.not_shown": "No demostrado",
    "tone.not_checked": "No comprobado",
    "state.hold": "En espera",
    "state.dont_pay": "No pague · no se pudo comprobar",
    "state.unverified": "No se pudieron ubicar estas fotos",
    "state.verified": "Las revisiones se sostuvieron",
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
