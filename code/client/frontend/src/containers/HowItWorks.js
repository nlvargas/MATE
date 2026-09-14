import React from 'react';
import { useI18n } from '../i18n';

// Sets/variables/constraints content, ported verbatim (including the actual
// formulas, not just their plain-English gloss) from the validated
// mate-redesign mockup's `how` object -- sourced there from the project's
// own developer manual. Formula/description strings carry real <sub> markup
// for subscripts, so they're rendered with dangerouslySetInnerHTML below;
// everything else is plain text.
const MATH = {
  en: {
    sets: [
      ["I", "student types, after grouping identical students"],
      ["NA ⊆ I", "student types with no answered preferences"],
      ["R", "attribute values (e.g. “Female”, “PUC”)"],
      ["T", "topics"],
      ["M", "sections"],
      ["G", "groups"],
      ["Gₜ, Gₘ, Gₜₘ ⊆ G", "groups with topic t, in section m, or both"],
    ],
    vars: [
      ["y[i,g]", "integer ≥ 0 — students of type i placed in group g"],
      ["w[g]", "binary — whether group g is actually formed"],
      ["z[i], z_max", "the rank type i receives, and the worst rank anyone receives"],
      ["q[g,r]", "integer — students with attribute value r in group g"],
      ["o[t], u[t,m]", "binary — whether topic t is used at all, and whether it's pinned to section m"],
      ["m[g], m_max", "non-response students in group g, and the worst concentration of them"],
    ],
    cons: [
      ["a", "Every student is placed in exactly one group.", "Σ<sub>g∈G</sub> y[i,g] = R<sub>i</sub>  ∀i∈I"],
      ["b", "A group can only receive students once it's switched on.", "y[i,g] ≤ w[g]·Q_max  ∀i∈I, g∈G"],
      ["c", "Exactly the target number of groups gets switched on.", "Σ<sub>g∈G</sub> w[g] = N_groups"],
      ["d", "Every active group's size stays within the min–max.", "Q_min·w[g] ≤ Σ<sub>i∈I</sub> y[i,g] ≤ Q_max·w[g]  ∀g∈G"],
      ["e", "Groups per topic stay within its configured range.", "LT<sub>t</sub> ≤ Σ<sub>g∈Gₜ</sub> w[g] ≤ UT<sub>t</sub>  ∀t∈T"],
      ["f–g", "A topic counts as “used” if assigned anywhere; at most UP topics are used overall.", "u[t,m] ≤ o[t]   ·   Σ<sub>t∈T</sub> o[t] ≤ UP"],
      ["h–i", "At most one non-responding student lands in the same group.", "Σ<sub>i∈NA</sub> y[i,g] ≤ 1 + m[g]  ∀g∈G   ·   m[g] ≤ m_max"],
      ["j–k", "Each type's assigned rank is recorded, and the worst one tracked.", "z[i] = Σ<sub>g∈G</sub> y[i,g]·P[i,g]   ·   z[i] ≤ z_max  ∀i∈I"],
      ["l–m", "Attribute-value counts stay within range — or are zero, if that's allowed.", "LR<sub>r</sub>(w[g]−p[g,r]) ≤ q[g,r] ≤ UR<sub>r</sub>(1−p[g,r])  ∀g∈G, r∈R"],
      ["n", "A section can't hold more students than its capacity.", "Σ<sub>i∈I</sub> Σ<sub>g∈Gₘ</sub> y[i,g] ≤ C<sub>m</sub>  ∀m∈M"],
      ["ñ", "A group only includes students available for that section.", "Σ<sub>g∈Gₘ</sub> y[i,g] ≤ D[i,m]  ∀i∈I, m∈M"],
      ["o", "If topics must stay in one section, every group on a topic shares it.", "Σ<sub>g∈Gₜₘ</sub> w[g] ≤ N_groups·u[t,m]  ∀t,m"],
      ["p", "A topic can't be placed in a section it's excluded from.", "u[t,m] = 0   where FD[t,m] = 0"],
    ],
  },
  es: {
    sets: [
      ["I", "tipos de alumno, tras agrupar a los estudiantes idénticos"],
      ["NA ⊆ I", "tipos de alumno sin preferencias respondidas"],
      ["R", "características (p. ej. “Femenino”, “PUC”)"],
      ["T", "temas"],
      ["M", "módulos (secciones)"],
      ["G", "grupos"],
      ["Gₜ, Gₘ, Gₜₘ ⊆ G", "grupos con el tema t, del módulo m, o de ambos"],
    ],
    vars: [
      ["y[i,g]", "entero ≥ 0 — estudiantes del tipo i asignados al grupo g"],
      ["w[g]", "binaria — si el grupo g llega a formarse"],
      ["z[i], z_max", "la preferencia con la que termina el tipo i, y la peor de todas"],
      ["q[g,r]", "entero — estudiantes con la característica r en el grupo g"],
      ["o[t], u[t,m]", "binaria — si el tema t se usa, y si queda fijado al módulo m"],
      ["m[g], m_max", "alumnos sin respuesta en el grupo g, y la peor concentración de ellos"],
    ],
    cons: [
      ["a", "Cada estudiante queda asignado a exactamente un grupo.", "Σ<sub>g∈G</sub> y[i,g] = R<sub>i</sub>  ∀i∈I"],
      ["b", "Un grupo solo puede recibir estudiantes si está activado.", "y[i,g] ≤ w[g]·Q_max  ∀i∈I, g∈G"],
      ["c", "Se activa exactamente la cantidad de grupos objetivo.", "Σ<sub>g∈G</sub> w[g] = N_grupos"],
      ["d", "Cada grupo activo mantiene su tamaño entre el mínimo y el máximo.", "Q_min·w[g] ≤ Σ<sub>i∈I</sub> y[i,g] ≤ Q_max·w[g]  ∀g∈G"],
      ["e", "Los grupos por tema se mantienen dentro de su rango configurado.", "LT<sub>t</sub> ≤ Σ<sub>g∈Gₜ</sub> w[g] ≤ UT<sub>t</sub>  ∀t∈T"],
      ["f–g", "Un tema cuenta como “usado” si se asigna en algún módulo; se usan a lo más UP temas.", "u[t,m] ≤ o[t]   ·   Σ<sub>t∈T</sub> o[t] ≤ UP"],
      ["h–i", "A lo más un alumno sin respuesta cae en el mismo grupo.", "Σ<sub>i∈NA</sub> y[i,g] ≤ 1 + m[g]  ∀g∈G   ·   m[g] ≤ m_max"],
      ["j–k", "Se registra la preferencia obtenida por cada tipo, y la peor de todas.", "z[i] = Σ<sub>g∈G</sub> y[i,g]·P[i,g]   ·   z[i] ≤ z_max  ∀i∈I"],
      ["l–m", "El conteo por característica se mantiene en rango — o es cero, si se permite.", "LR<sub>r</sub>(w[g]−p[g,r]) ≤ q[g,r] ≤ UR<sub>r</sub>(1−p[g,r])  ∀g∈G, r∈R"],
      ["n", "Un módulo no puede recibir más estudiantes que su capacidad.", "Σ<sub>i∈I</sub> Σ<sub>g∈Gₘ</sub> y[i,g] ≤ C<sub>m</sub>  ∀m∈M"],
      ["ñ", "Un grupo solo incluye estudiantes disponibles para ese módulo.", "Σ<sub>g∈Gₘ</sub> y[i,g] ≤ D[i,m]  ∀i∈I, m∈M"],
      ["o", "Si los temas deben quedar en un solo módulo, todos sus grupos lo comparten.", "Σ<sub>g∈Gₜₘ</sub> w[g] ≤ N_grupos·u[t,m]  ∀t,m"],
      ["p", "Un tema no puede quedar en un módulo del que está excluido.", "u[t,m] = 0   donde FD[t,m] = 0"],
    ],
  },
};

const OBJ_FORMULA = {
  en: "min  Σ<sub>i∈I</sub> N<sub>i</sub>·z[i]  +  K·(z_max + m_max)",
  es: "mín  Σ<sub>i∈I</sub> N<sub>i</sub>·z[i]  +  K·(z_max + m_max)",
};

export default function HowItWorks({ onClose }) {
  const { t, lang } = useI18n();
  const m = MATH[lang] || MATH.en;
  const objFormula = OBJ_FORMULA[lang] || OBJ_FORMULA.en;

  return (
    <div className="modal-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-panel" role="dialog" aria-modal="true">
        <div className="modal-head">
          <h2>{t("howTitle")}</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>
        <div className="modal-body">
          <p>{t("howIntro")}</p>

          <h3>{t("howSetsTitle")}</h3>
          {m.sets.map(([sym, desc]) => (
            <div className="var-row" key={sym}><span className="v-sym mono">{sym}</span><span>{desc}</span></div>
          ))}

          <h3>{t("howVarsTitle")}</h3>
          {m.vars.map(([sym, desc]) => (
            <div className="var-row" key={sym}><span className="v-sym mono">{sym}</span><span>{desc}</span></div>
          ))}

          <h3>{t("howConsTitle")}</h3>
          {m.cons.map(([tag, name, formula]) => (
            <div className="con-row" key={tag}>
              <div className="con-head"><span className="con-name">{name}</span></div>
              <div className="con-formula" dangerouslySetInnerHTML={{ __html: formula }} />
            </div>
          ))}
          <p style={{ marginTop: 10, fontSize: 11.5 }}>{t("howDomains")}</p>

          <h3>{t("howObjTitle")}</h3>
          <p style={{ marginBottom: 10 }}>{t("howObj")}</p>
          <div className="modal-box con-formula" dangerouslySetInnerHTML={{ __html: objFormula }} />
          <p style={{ marginTop: 8, fontSize: 11.5 }}>{t("howObjNote")}</p>

          <h3>{t("howExecTitle")}</h3>
          <div className="modal-box">{t("howExec")}</div>
          <div className="modal-cite">{t("howCite")}</div>
        </div>
      </div>
    </div>
  );
}
