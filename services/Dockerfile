# Image commune aux quatre microservices. Construite depuis la racine du dépôt :
#   docker build -f services/Dockerfile --build-arg SERVICE=auth .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Compte système sans privilèges : le service ne tourne jamais en root.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin scolaris

WORKDIR /srv
ARG SERVICE

# 1. Dépendances externes : couche mise en cache tant que requirements.txt ne change pas.
COPY services/${SERVICE}/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 120 setuptools wheel \
 && pip install --retries 10 --timeout 120 -r /tmp/requirements.txt

# 2. Bibliothèque commune du projet (change souvent, installation sans téléchargement).
COPY libs/common /tmp/common
RUN pip install --no-cache-dir --no-build-isolation --no-deps /tmp/common && rm -rf /tmp/common /tmp/requirements.txt

COPY services/${SERVICE}/app ./app

USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/sante', timeout=2)"

# --no-server-header : la version d'uvicorn n'est pas divulguée.
CMD ["uvicorn", "app.main:creer_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--no-access-log"]
