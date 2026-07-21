import { LEGAL_NOTES } from "@/content/texts";
import { openLink } from "@/lib/telegram";

interface Props {
  kind: keyof typeof LEGAL_NOTES;
}

// Мелкий текст под CTA-кнопкой со ссылкой на юридический документ.
// URL строится от window.location.origin: Telegram.WebApp.openLink принимает
// только абсолютные URL, а домен Mini App и статики /legal/* — один и тот же.
export default function LegalNote({ kind }: Props) {
  const { prefix, linkLabel, doc } = LEGAL_NOTES[kind];
  return (
    <p className="mt-3 text-center text-xs leading-snug text-white/50">
      {prefix}
      <button
        onClick={() => openLink(`${window.location.origin}/legal/${doc}.html`)}
        className="underline"
      >
        {linkLabel}
      </button>
    </p>
  );
}
