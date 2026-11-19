# Passerelle : construit le back-office React puis le sert avec Nginx non privilégié.
#   docker build -f gateway/Dockerfile .
FROM node:22-alpine AS construction
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
# Correctifs de sécurité du système appliqués à chaque construction (contrôlés par Trivy),
# puis retour immédiat au compte non privilégié de l'image (UID 101).
USER root
RUN apk upgrade --no-cache
USER 101
COPY gateway/nginx.conf /etc/nginx/nginx.conf
COPY gateway/entetes_securite.conf /etc/nginx/entetes_securite.conf
COPY --from=construction /web/dist /usr/share/nginx/html
EXPOSE 8443 8080
