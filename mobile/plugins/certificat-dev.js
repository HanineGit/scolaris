/**
 * Module de configuration Expo : confiance dans le certificat auto-signé de
 * développement, UNIQUEMENT dans les versions de débogage (debug-overrides).
 *
 * - Le trafic en clair reste interdit vers l'API (cleartextTrafficPermitted=false).
 * - Le certificat de développement n'est jamais accepté par une version publiée :
 *   celle-ci n'utilise que les autorités du système, plus l'épinglage de clé.
 */
const fs = require("fs");
const path = require("path");
const { withAndroidManifest, withDangerousMod } = require("expo/config-plugins");

const XML = `<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <base-config cleartextTrafficPermitted="false">
    <trust-anchors>
      <certificates src="system" />
    </trust-anchors>
  </base-config>
  <!-- Le serveur Metro de développement reste joignable en clair sur la machine locale. -->
  <domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="false">10.0.2.2</domain>
    <domain includeSubdomains="false">127.0.0.1</domain>
  </domain-config>
  <debug-overrides>
    <trust-anchors>
      <certificates src="@raw/scolaris_dev" />
      <certificates src="system" />
    </trust-anchors>
  </debug-overrides>
</network-security-config>
`;

module.exports = function certificatDev(config) {
  config = withDangerousMod(config, ["android", async (cfg) => {
    const res = path.join(cfg.modRequest.platformProjectRoot, "app", "src", "main", "res");
    fs.mkdirSync(path.join(res, "xml"), { recursive: true });
    fs.mkdirSync(path.join(res, "raw"), { recursive: true });
    fs.writeFileSync(path.join(res, "xml", "network_security_config.xml"), XML);
    const certificat = path.join(cfg.modRequest.projectRoot, "..", "secrets", "tls_cert");
    if (fs.existsSync(certificat)) fs.copyFileSync(certificat, path.join(res, "raw", "scolaris_dev.pem"));
    return cfg;
  }]);
  return withAndroidManifest(config, (cfg) => {
    const application = cfg.modResults.manifest.application[0];
    application.$["android:networkSecurityConfig"] = "@xml/network_security_config";
    return cfg;
  });
};
