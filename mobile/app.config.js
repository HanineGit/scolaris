// Ajoute à la configuration les empreintes TLS épinglées, produites par
// scripts/generer_secrets.py (clé active de la passerelle et clé de secours).
const fs = require("fs");
const path = require("path");

module.exports = ({ config }) => {
  const fichier = path.join(__dirname, "empreintes_tls.json");
  const empreintesTls = fs.existsSync(fichier) ? JSON.parse(fs.readFileSync(fichier, "utf8")) : [];
  return {
    ...config,
    extra: { ...config.extra, apiUrl: process.env.SCOLARIS_API_URL ?? config.extra.apiUrl, empreintesTls },
  };
};
