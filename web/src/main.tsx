import "@fontsource-variable/plus-jakarta-sans";
import "./styles.css";

import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import type { Role } from "./api";
import Activation from "./pages/Activation";
import Connexion from "./pages/Connexion";
import Reclamations from "./pages/Reclamations";
import Securite from "./pages/Securite";
import Verification from "./pages/Verification";
import Calendrier from "./pages/admin/Calendrier";
import Classes from "./pages/admin/Classes";
import Deliberation from "./pages/admin/Deliberation";
import TableauDeBord from "./pages/admin/TableauDeBord";
import AjoutEtudiant from "./pages/admin/AjoutEtudiant";
import Audit from "./pages/admin/Audit";
import Comptes from "./pages/admin/Comptes";
import Etudiants from "./pages/admin/Etudiants";
import FicheEtudiant from "./pages/admin/FicheEtudiant";
import Matieres from "./pages/admin/Matieres";
import Grille from "./pages/enseignant/Grille";
import MesMatieres from "./pages/enseignant/MesMatieres";
import Notes from "./pages/enseignant/Notes";
import Saisie from "./pages/enseignant/Saisie";
import Statistiques from "./pages/enseignant/Statistiques";
import { FournisseurSession, useSession } from "./session";
import { appliquerTheme } from "./theme";
import { Gabarit, Message } from "./ui";

appliquerTheme();

/**
 * Garde d'accès côté interface : elle évite d'afficher un écran inutile, mais
 * n'est pas une protection. Chaque service revérifie le rôle (et l'affectation).
 */
function Reserve({ role, children }: { role: Role | Role[]; children: ReactNode }) {
  const { utilisateur } = useSession();
  if (!utilisateur) return <Navigate to="/connexion" replace />;
  if (!(Array.isArray(role) ? role : [role]).includes(utilisateur.role)) {
    return <Gabarit fil={["Accès refusé"]}><Message type="er">Cette page n'est pas accessible avec votre rôle.</Message></Gabarit>;
  }
  return <>{children}</>;
}

function Accueil() {
  const { utilisateur } = useSession();
  if (!utilisateur) return <Navigate to="/connexion" replace />;
  return <Navigate to={utilisateur.role === "ADMINISTRATEUR" ? "/admin" : "/enseignant/matieres"} replace />;
}

const ens = (e: ReactNode) => <Reserve role="ENSEIGNANT">{e}</Reserve>;
const adm = (e: ReactNode) => <Reserve role="ADMINISTRATEUR">{e}</Reserve>;
const personnel = (e: ReactNode) => <Reserve role={["ENSEIGNANT", "ADMINISTRATEUR"]}>{e}</Reserve>;

createRoot(document.getElementById("racine")!).render(
  <StrictMode>
    <FournisseurSession>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Accueil />} />
          <Route path="/connexion" element={<Connexion />} />
          <Route path="/activation" element={<Activation />} />
          <Route path="/verification/:code" element={<Verification />} />
          <Route path="/securite" element={personnel(<Securite />)} />
          <Route path="/enseignant/grille" element={ens(<Grille />)} />
          <Route path="/enseignant/statistiques" element={ens(<Statistiques />)} />
          <Route path="/enseignant/reclamations" element={ens(<Reclamations role="ENSEIGNANT" />)} />
          <Route path="/admin" element={adm(<TableauDeBord />)} />
          <Route path="/admin/classes" element={adm(<Classes />)} />
          <Route path="/admin/calendrier" element={adm(<Calendrier />)} />
          <Route path="/admin/deliberation" element={adm(<Deliberation />)} />
          <Route path="/admin/reclamations" element={adm(<Reclamations role="ADMINISTRATEUR" />)} />
          <Route path="/enseignant/matieres" element={ens(<MesMatieres />)} />
          <Route path="/enseignant/saisie" element={ens(<Saisie />)} />
          <Route path="/enseignant/notes" element={ens(<Notes />)} />
          <Route path="/admin/etudiants" element={adm(<Etudiants />)} />
          <Route path="/admin/etudiants/nouveau" element={adm(<AjoutEtudiant />)} />
          <Route path="/admin/etudiants/:id" element={adm(<FicheEtudiant />)} />
          <Route path="/admin/matieres" element={adm(<Matieres />)} />
          <Route path="/admin/comptes" element={adm(<Comptes />)} />
          <Route path="/admin/audit" element={adm(<Audit />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </FournisseurSession>
  </StrictMode>,
);
