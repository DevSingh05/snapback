import { apiFetch, apiFetchRead, dataMode } from "../api";
import type { TourPrepPack } from "../contracts";

export type Lang = "en" | "es";

export class PackNeedsToken extends Error {}

export type PackTarget =
  { kind: "place"; propertyId: string; planKey: string | null } | { kind: "case"; caseId: string };

// Synthetic sample packs for fixture mode. They are labelled FIXTURE on screen and describe no
// real home. The API writes the real ones; this only stands in when no API is configured.
const COSTAR = { en: "CoStar record", es: "Registro de CoStar" };
const AS_OF = { en: "as of CoStar's last research", es: "según la última investigación de CoStar" };

const FIXTURE_PACKS: Record<Lang, TourPrepPack> = {
  en: {
    source: "fixture",
    lang: "en",
    title: "Tour prep",
    subtitle: "Be your own realtor: what the record says, what to ask, what to do first.",
    note: "Written by code from records. It says nothing about any person.",
    as_of: AS_OF.en,
    facts_heading: "What the record says",
    questions_heading: "Questions to ask",
    pay_heading: "Before you pay",
    facts: [
      {
        key: "home",
        text: "1 bed / 1 bath, built 1998, 12 floors",
        sources: [COSTAR.en],
        as_of: AS_OF.en,
      },
      {
        key: "price",
        text: `$1,450 to $1,600 a month; 3 units reported available ${AS_OF.en}`,
        sources: [COSTAR.en],
        as_of: AS_OF.en,
      },
      {
        key: "building",
        text: "Building: not a walk-up; elevator on record; individual utility meters",
        sources: [COSTAR.en],
        as_of: AS_OF.en,
      },
      {
        key: "owner",
        text: "Owner of record: a company owner",
        sources: ["County record"],
      },
      {
        key: "imagery",
        text: "A 3D scan of this building exists; aerial photo captured Jun 1, 2025",
        sources: ["Matterport", "Vexcel"],
      },
    ],
    questions: [
      {
        key: "licence",
        text: "Ask the agent for their Texas real estate licence number, then look it up yourself at trec.texas.gov.",
        sources: [],
      },
      {
        key: "landlord",
        text: "Check that the landlord named on the lease matches the owner of record, which is a company.",
        sources: [],
      },
      {
        key: "pay",
        text: "Ask exactly who you pay and through which official channel, and get it in writing.",
        sources: [],
      },
      {
        key: "fees",
        text: "Ask for the total move-in cost and the application fee in writing. We hold no fee data for this home.",
        sources: [],
      },
      {
        key: "tour",
        text: "At the tour, check the water pressure, the AC and the appliances, and that the unit number matches the lease.",
        sources: [],
      },
    ],
    before_you_pay: [
      "Pay nothing before you have toured the home in person and read the lease.",
      "Pay only through the channel written on the lease or on the office's own website. Never pay cash, Zelle or gift cards to a person.",
      "If the payment details change at the last minute, stop and call the office on a number you looked up yourself.",
    ],
  },
  es: {
    source: "fixture",
    lang: "es",
    title: "Prepara tu visita",
    subtitle: "Sé tu propio agente: lo que dice el registro, qué preguntar y qué hacer antes.",
    note: "Escrito por código a partir de registros. No dice nada sobre ninguna persona.",
    as_of: AS_OF.es,
    facts_heading: "Lo que dice el registro",
    questions_heading: "Preguntas para hacer",
    pay_heading: "Antes de pagar",
    facts: [
      {
        key: "home",
        text: "1 bed / 1 bath, construido en 1998, 12 pisos",
        sources: [COSTAR.es],
        as_of: AS_OF.es,
      },
      {
        key: "price",
        text: `$1,450 a $1,600 al mes; 3 unidades reportadas como disponibles ${AS_OF.es}`,
        sources: [COSTAR.es],
        as_of: AS_OF.es,
      },
      {
        key: "building",
        text: "Edificio: no es un edificio de escaleras; elevador en el registro; medidores de servicios individuales",
        sources: [COSTAR.es],
        as_of: AS_OF.es,
      },
      {
        key: "owner",
        text: "Dueño en el registro: una empresa",
        sources: ["Registro del condado"],
      },
      {
        key: "imagery",
        text: "Existe un escaneo 3D de este edificio; foto aérea tomada el 1 jun 2025",
        sources: ["Matterport", "Vexcel"],
      },
    ],
    questions: [
      {
        key: "licence",
        text: "Pide al agente su número de licencia de bienes raíces de Texas y búscalo tú mismo en trec.texas.gov.",
        sources: [],
      },
      {
        key: "landlord",
        text: "Confirma que el arrendador que aparece en el contrato coincide con el dueño en el registro, que es una empresa.",
        sources: [],
      },
      {
        key: "pay",
        text: "Pregunta exactamente a quién pagas y por qué canal oficial, y pídelo por escrito.",
        sources: [],
      },
      {
        key: "fees",
        text: "Pide por escrito el costo total de mudanza y la cuota de solicitud. No tenemos datos de cuotas de esta vivienda.",
        sources: [],
      },
      {
        key: "tour",
        text: "En la visita, revisa la presión del agua, el aire acondicionado y los aparatos, y que el número de unidad coincida con el contrato.",
        sources: [],
      },
    ],
    before_you_pay: [
      "No pagues nada antes de visitar la vivienda en persona y leer el contrato.",
      "Paga solo por el canal escrito en el contrato o en el sitio web de la oficina. Nunca pagues en efectivo, por Zelle ni con tarjetas de regalo a una persona.",
      "Si los datos de pago cambian a último momento, detente y llama a la oficina a un número que hayas buscado tú mismo.",
    ],
  },
};

async function failure(res: Response): Promise<Error> {
  let detail = "";
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = ` ${body.detail}`;
  } catch {
    // not JSON; the status is enough
  }
  return new Error(`The server answered ${res.status}.${detail}`.trim());
}

export async function fetchPack(
  target: PackTarget,
  lang: Lang,
  signal?: AbortSignal,
): Promise<TourPrepPack> {
  if (dataMode() === "fixture") return FIXTURE_PACKS[lang];
  let res: Response;
  if (target.kind === "place") {
    const q = new URLSearchParams({ lang });
    if (target.planKey) q.set("plan_key", target.planKey);
    res = await apiFetch(`/places/${encodeURIComponent(target.propertyId)}/tour-prep?${q}`, {
      signal,
    });
  } else {
    const path = `/cases/${encodeURIComponent(target.caseId)}/tour-prep?lang=${lang}`;
    // With no key in this browser we still ask, with no header: a recorded case has no secret
    // and answers; a case that has one answers 401, which says "open it where you checked".
    res = await (apiFetchRead(path, target.caseId, { signal }) ?? apiFetch(path, { signal }));
    if (res.status === 401) throw new PackNeedsToken();
  }
  if (!res.ok) throw await failure(res);
  return (await res.json()) as TourPrepPack;
}

// The pack as plain text for Copy: the API's own lines, nothing added.
export function packToText(pack: TourPrepPack): string {
  const lines = [pack.title, pack.subtitle, ""];
  lines.push(pack.facts_heading.toUpperCase());
  for (const f of pack.facts) {
    lines.push(`- ${f.text} (${[...f.sources, ...(f.as_of ? [f.as_of] : [])].join(", ")})`);
  }
  lines.push("", pack.questions_heading.toUpperCase());
  pack.questions.forEach((q, i) => lines.push(`${i + 1}. ${q.text}`));
  lines.push("", pack.pay_heading.toUpperCase());
  pack.before_you_pay.forEach((s, i) => lines.push(`${i + 1}. ${s}`));
  lines.push("", `${pack.source === "live" ? "LIVE" : "FIXTURE"}. ${pack.note}`);
  return lines.join("\n");
}
