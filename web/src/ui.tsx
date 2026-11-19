import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { ErreurApi, api } from "./api";
import { dateHeure, initiales } from "./format";
import { Icone } from "./icons";
import { useSession } from "./session";
import { useTheme } from "./theme";

/* ---------- Gabarit : en-tête, menu selon le rôle, fil d'Ariane ---------- */

const MENUS = {
  ENSEIGNANT: [
    { titre: "Enseignement", liens: [
      { vers: "/enseignant/matieres", icone: "book", libelle: "Mes matières" },
      { vers: "/enseignant/grille", icone: "grid", libelle: "Saisie par classe" },
      { vers: "/enseignant/saisie", icone: "edit", libelle: "Saisie individuelle" },
      { vers: "/enseignant/notes", icone: "list", libelle: "Consultation des notes" },
    ] },
    { titre: "Suivi", liens: [
      { vers: "/enseignant/statistiques", icone: "bars", libelle: "Statistiques" },
      { vers: "/enseignant/reclamations", icone: "message", libelle: "Réclamations" },
    ] },
    { titre: "Compte", liens: [{ vers: "/securite", icone: "shield", libelle: "Sécurité du compte" }] },
  ],
  ADMINISTRATEUR: [
    { titre: "Pilotage", liens: [
      { vers: "/admin", icone: "home", libelle: "Tableau de bord" },
    ] },
    { titre: "Scolarité", liens: [
      { vers: "/admin/etudiants", icone: "users", libelle: "Étudiants" },
      { vers: "/admin/classes", icone: "layers", libelle: "Classes et inscriptions" },
      { vers: "/admin/matieres", icone: "book", libelle: "Matières et publication" },
      { vers: "/admin/calendrier", icone: "calendar", libelle: "Calendrier et saisie" },
    ] },
    { titre: "Résultats", liens: [
      { vers: "/admin/deliberation", icone: "award", libelle: "Délibération" },
      { vers: "/admin/reclamations", icone: "message", libelle: "Réclamations" },
    ] },
    { titre: "Administration", liens: [
      { vers: "/admin/comptes", icone: "key", libelle: "Comptes du personnel" },
      { vers: "/admin/audit", icone: "log", libelle: "Journal d'audit" },
      { vers: "/securite", icone: "shield", libelle: "Sécurité du compte" },
    ] },
  ],
};

export function BoutonTheme() {
  const [theme, basculer] = useTheme();
  const sombre = theme === "dark";
  return (
    <button className="ic" onClick={basculer} aria-label={sombre ? "Passer au thème clair" : "Passer au thème sombre"}
            title={sombre ? "Thème clair" : "Thème sombre"}>
      <Icone nom={sombre ? "sun" : "moon"} taille={17} />
    </button>
  );
}

export function EnTete({ droite }: { droite?: ReactNode }) {
  return (
    <header className="hd">
      <div className="brand"><span className="bm">S</span>Scolaris<span className="bs">Gestion des notes</span></div>
      <div className="hr">{droite ?? <BoutonTheme />}</div>
    </header>
  );
}

export function Gabarit({ fil, children }: { fil: string[]; children: ReactNode }) {
  const { utilisateur, minutesRestantes, quitter } = useSession();
  if (!utilisateur || utilisateur.role === "ETUDIANT") return null;
  const role = utilisateur.role === "ADMINISTRATEUR" ? "Administrateur" : "Enseignant";
  return (
    <>
      <EnTete droite={<>
        <span className={`tm${minutesRestantes <= 2 ? " alerte" : ""}`}><Icone nom="clock" taille={14} />Session : {minutesRestantes} min</span>
        <BoutonTheme />
        <Cloche />
        <span className="who">
          <span className="av">{initiales(utilisateur.nom, utilisateur.prenom)}</span>
          <span><b>{utilisateur.prenom} {utilisateur.nom}</b><small>{role}</small></span>
        </span>
        <button className="lo" onClick={() => void quitter()}><Icone nom="out" taille={15} />Déconnexion</button>
      </>} />
      <div className="wrap">
        <nav className="nv" aria-label="Menu principal">
          {MENUS[utilisateur.role].map((section) => (
            <div key={section.titre}>
              {section.titre && <div className="nsec">{section.titre}</div>}
              {section.liens.map((l) => (
                <NavLink key={l.vers} to={l.vers} end><Icone nom={l.icone} />{l.libelle}</NavLink>
              ))}
            </div>
          ))}
        </nav>
        <main className="mn">
          <div className="crumb">
            {fil.map((f, i) => i === fil.length - 1 ? <b key={i}>{f}</b> : <span key={i}>{f}<span className="sep">/</span></span>)}
          </div>
          {children}
        </main>
      </div>
    </>
  );
}

/* ---------- Composants de formulaire ---------- */

export function Champ({ libelle, requis, erreur, aide, children }: {
  libelle: string; requis?: boolean; erreur?: string | null; aide?: string; children: ReactNode;
}) {
  // Le champ est placé dans son libellé : il est ainsi associé à son nom accessible.
  return (
    <div className="fg">
      <label><span className="lbl">{libelle}{requis && <em> *</em>}</span>{children}</label>
      {erreur ? <p className="help e" role="alert">{erreur}</p> : aide ? <p className="help">{aide}</p> : null}
    </div>
  );
}

export function Message({ type, children }: { type: "er" | "in" | "wa" | "ok"; children: ReactNode }) {
  const icone = { er: "alert", wa: "alert", in: "info", ok: "check" }[type];
  // La classe « info » évite toute collision avec la classe « in » des champs de saisie.
  return <div className={`msg ${type === "in" ? "info" : type}`} role={type === "er" ? "alert" : "status"}><Icone nom={icone} /><span>{children}</span></div>;
}

export function Statut({ ton, children }: { ton: string; children: ReactNode }) {
  return <span className={`st ${ton}`}>{children}</span>;
}

export function Modale({ titre, onFermer, pied, children, largeur }: {
  titre: string; onFermer: () => void; pied?: ReactNode; children: ReactNode; largeur?: number;
}) {
  useEffect(() => {
    const echap = (e: KeyboardEvent) => e.key === "Escape" && onFermer();
    window.addEventListener("keydown", echap);
    return () => window.removeEventListener("keydown", echap);
  }, [onFermer]);
  return (
    <div className="ov" role="dialog" aria-modal="true" aria-label={titre}>
      <div className="dlg" style={largeur ? { width: largeur } : undefined}>
        <div className="dh"><h2>{titre}</h2><button className="fermer" onClick={onFermer} aria-label="Fermer"><Icone nom="x" taille={18} /></button></div>
        <div className="db">{children}</div>
        {pied && <div className="df">{pied}</div>}
      </div>
    </div>
  );
}

export function Pagination({ page, total, taille, onPage }: { page: number; total: number; taille: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / taille));
  const debut = total === 0 ? 0 : (page - 1) * taille + 1;
  const fin = Math.min(total, page * taille);
  const visibles = Array.from({ length: pages }, (_, i) => i + 1).filter((p) => p === 1 || p === pages || Math.abs(p - page) <= 1);
  return (
    <div className="pg">
      <span>{debut} à {fin} sur {total}</span>
      <span className="n">
        {visibles.map((p, i) => (
          <span key={p} style={{ display: "inline-flex", gap: 4 }}>
            {i > 0 && p - visibles[i - 1] > 1 && <span style={{ alignSelf: "center" }}>…</span>}
            <button className={p === page ? "on" : ""} onClick={() => onPage(p)} aria-current={p === page}>{p}</button>
          </span>
        ))}
      </span>
    </div>
  );
}

export function messageErreur(e: unknown): string {
  if (e instanceof ErreurApi) {
    if (e.details.length) return `${e.message} ${e.details.map((d) => `${d.champ} : ${d.regle}`).join(" ; ")}`;
    return e.message;
  }
  return "Une erreur est survenue.";
}

/** Chargement d'une ressource avec état d'attente et d'erreur. */
export function useChargement<T>(charger: () => Promise<T>, deps: unknown[]) {
  const [donnees, setDonnees] = useState<T | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const recharger = useCallback(() => {
    setEnCours(true);
    charger().then((d) => { setDonnees(d); setErreur(null); })
      .catch((e) => setErreur(messageErreur(e)))
      .finally(() => setEnCours(false));
  }, deps);
  useEffect(recharger, [recharger]);
  return { donnees, erreur, enCours, recharger };
}

/* ---------- Centre de notifications (F28) ---------- */

interface Notification { id: string; categorie: string; titre: string; message: string; lien: string | null; creee_le: string; lue: boolean }

const ICONES_CATEGORIE: Record<string, string> = { NOTES: "file", RECLAMATION: "message", SECURITE: "shield", COMPTE: "key" };

export function Cloche() {
  const [ouverte, setOuverte] = useState(false);
  const [donnees, setDonnees] = useState<{ non_lues: number; elements: Notification[] } | null>(null);
  const zone = useRef<HTMLDivElement>(null);
  const aller = useNavigate();
  const charger = useCallback(() => {
    api.get<{ non_lues: number; elements: Notification[] }>("/notifications?limite=15").then(setDonnees).catch(() => undefined);
  }, []);
  useEffect(() => {
    charger();
    const minuterie = window.setInterval(charger, 60_000);
    return () => window.clearInterval(minuterie);
  }, [charger]);
  useEffect(() => {
    const dehors = (e: MouseEvent) => { if (zone.current && !zone.current.contains(e.target as Node)) setOuverte(false); };
    document.addEventListener("mousedown", dehors);
    return () => document.removeEventListener("mousedown", dehors);
  }, []);
  async function ouvrir(n: Notification) {
    if (!n.lue) await api.post(`/notifications/${n.id}/lecture`).catch(() => undefined);
    setOuverte(false);
    charger();
    // Seuls des chemins internes sont acceptés par le service : aucun lien externe n'est suivi.
    if (n.lien?.startsWith("/") && !n.lien.startsWith("//")) aller(n.lien);
  }
  const nonLues = donnees?.non_lues ?? 0;
  return (
    <div ref={zone} style={{ position: "relative" }}>
      <button className="ic" onClick={() => setOuverte((o) => !o)} aria-label={`Notifications (${nonLues} non lues)`} aria-expanded={ouverte}>
        <Icone nom="bell" taille={17} />
        {nonLues > 0 && <span className="badge">{nonLues > 9 ? "9+" : nonLues}</span>}
      </button>
      {ouverte && (
        <div className="menu-deroulant" role="menu">
          <div className="bx-h"><h3>Notifications</h3>
            {nonLues > 0 && <button className="lien" onClick={() => void api.post("/notifications/lecture").then(charger)}>Tout marquer comme lu</button>}
          </div>
          <ul className="chrono" style={{ maxHeight: 380, overflowY: "auto" }}>
            {(donnees?.elements ?? []).map((n) => (
              <li key={n.id} role="menuitem" tabIndex={0} style={{ cursor: "pointer", background: n.lue ? undefined : "var(--pr-soft)" }}
                  onClick={() => void ouvrir(n)} onKeyDown={(e) => e.key === "Enter" && void ouvrir(n)}>
                <span style={{ color: n.categorie === "SECURITE" ? "var(--er)" : "var(--pr)", marginTop: 2 }}><Icone nom={ICONES_CATEGORIE[n.categorie] ?? "info"} /></span>
                <span style={{ minWidth: 0 }}><b style={{ display: "block", fontSize: 13 }}>{n.titre}</b>
                  <span style={{ color: "var(--mu)", fontSize: 12.5 }}>{n.message}</span>
                  <span style={{ display: "block", color: "var(--fa)", fontSize: 11.5, marginTop: 3 }}>{dateHeure(n.creee_le)}</span></span>
              </li>
            ))}
          </ul>
          {donnees?.elements.length === 0 && <p className="vide">Aucune notification.</p>}
        </div>
      )}
    </div>
  );
}

/* ---------- Indicateurs et graphiques ---------- */

export function Indicateur({ libelle, valeur, detail, icone, ton }: {
  libelle: string; valeur: ReactNode; detail?: ReactNode; icone: string; ton?: "ok" | "er" | "wa";
}) {
  return (
    <div className="ind">
      <span className={`pic${ton ? ` ${ton}` : ""}`}><Icone nom={icone} taille={19} /></span>
      <div><span>{libelle}</span><b>{valeur}</b>{detail && <small>{detail}</small>}</div>
    </div>
  );
}

/** Histogramme simple et accessible : la valeur de chaque barre est lisible sans survol. */
export function Barres({ series, seuilBas }: { series: { libelle: string; valeur: number }[]; seuilBas?: (i: number) => boolean }) {
  const max = Math.max(1, ...series.map((s) => s.valeur));
  return (
    <div className="barres" role="img" aria-label={series.map((s) => `${s.libelle} : ${s.valeur}`).join(", ")}>
      {series.map((s, i) => (
        <div key={s.libelle}>
          <b style={{ fontSize: 11.5, color: "var(--tx2)" }}>{s.valeur || ""}</b>
          <i className={seuilBas?.(i) ? "bas" : ""} style={{ height: `${(s.valeur / max) * 100}%` }} />
          <span>{s.libelle}</span>
        </div>
      ))}
    </div>
  );
}
