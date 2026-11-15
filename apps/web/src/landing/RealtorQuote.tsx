import { loadLang, type Lang } from "../lang";
import "./landing.css";

// A real realtor's words about who SNAPBACK is for, on the front door, under the checks and above the footer. The
// quote is his, word for word, and always shown in English; in Spanish a translation sits under
// it in smaller text. The one line above it is ours. The rest of the front page is English only,
// so this follows the saved language choice (src/lang.ts) without changing anything around it.

export const REALTOR_QUOTE =
  "If he can add in additional safety features for preventing further scams and financial scams, I think this would be a very good app to have in the marketplace.";

export const REALTOR_NAME = "Ashwin Veeravalli";

const COPY: Record<
  Lang,
  { kicker: string; context: string; translation: string | null; byline: string }
> = {
  en: {
    kicker: "From a realtor",
    context: "Rental tour prep, with scam safety built in.",
    translation: null,
    byline: "Realtor, The Agency, Los Gatos CA",
  },
  es: {
    kicker: "De un agente inmobiliario",
    context: "Preparación de visitas a alquileres, con protección contra estafas incluida.",
    translation:
      "Si puede añadir funciones de seguridad adicionales para evitar más estafas y fraudes financieros, creo que sería una muy buena aplicación para tener en el mercado.",
    byline: "Agente inmobiliario, The Agency, Los Gatos, CA",
  },
};

export function RealtorQuote({ lang = loadLang() }: { lang?: Lang }) {
  const c = COPY[lang];
  return (
    <figure className="rq" data-testid="realtor-quote" lang="en">
      <p className="rq-kicker ui-mono" lang={lang}>
        {c.kicker}
      </p>
      <p className="rq-context" lang={lang}>
        {c.context}
      </p>
      <blockquote className="rq-quote">
        <p>{`“${REALTOR_QUOTE}”`}</p>
        {c.translation && (
          <p className="rq-es" lang="es" data-testid="realtor-quote-es">
            {c.translation}
          </p>
        )}
      </blockquote>
      <figcaption className="rq-by" lang={lang}>
        <strong>{REALTOR_NAME}</strong>
        {`, ${c.byline}`}
      </figcaption>
    </figure>
  );
}
