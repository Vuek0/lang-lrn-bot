#!/usr/bin/env bash
# Deploys the bot on the server. Runs ON THE SERVER, from a clone of this repository.
#
# GitHub Actions calls it over SSH with a key that can do nothing else. In ~/.ssh/authorized_keys:
#   command="/home/ubuntu/lang-lrn-bot/scripts/deploy.sh",restrict ssh-ed25519 AAAA... github-deploy
# so whatever the client asks for, only this script runs; the request ("deploy <sha>") arrives
# in $SSH_ORIGINAL_COMMAND and is strictly validated.
#
# Manual use on the server:  ./scripts/deploy.sh deploy <40-char commit sha from main>
#
# Safety:
# - only commits that are on origin/main can be deployed;
# - the image comes from this repository's public GHCR package, tagged with that commit;
# - if the new version doesn't stay up, the previous one is restored.

set -euo pipefail

main() {  # everything in a function: bash reads the whole file before git checkout replaces it
  local request="${SSH_ORIGINAL_COMMAND:-$*}"
  local action sha extra
  read -r action sha extra <<<"$request" || true
  if [[ "${action:-}" != "deploy" || ! "${sha:-}" =~ ^[0-9a-f]{40}$ || -n "${extra:-}" ]]; then
    echo "usage: deploy <40-char commit sha>" >&2
    exit 2
  fi

  local app_dir
  app_dir="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
  cd "$app_dir"
  [[ -f .env ]] || { echo "no .env in $app_dir — create it first (see README)" >&2; exit 1; }

  git fetch --quiet origin main
  if ! git merge-base --is-ancestor "$sha" origin/main; then
    echo "refusing to deploy $sha: it is not on origin/main" >&2
    exit 1
  fi

  local image previous_sha previous_override=""
  image="$(image_name)"
  previous_sha="$(cat .deployed 2>/dev/null || true)"
  [[ -f docker-compose.override.yml ]] && previous_override="$(cat docker-compose.override.yml)"

  echo "deploying ${sha:0:12} (previous: ${previous_sha:0:12})"
  git checkout --quiet --detach "$sha"
  printf 'services:\n  bot:\n    image: %s:%s\n' "$image" "$sha" > docker-compose.override.yml
  docker compose pull --quiet bot
  docker compose up -d --remove-orphans

  if healthy; then
    echo "$sha" > .deployed
    docker image prune -af --filter "until=168h" >/dev/null || true  # old unused images (a week+)
    echo "deployed ${sha:0:12} ✔"
    return 0
  fi

  echo "new version is not running, last logs:" >&2
  docker compose logs --tail 40 bot >&2 || true
  if [[ -n "$previous_sha" && -n "$previous_override" ]]; then
    echo "rolling back to ${previous_sha:0:12}" >&2
    git checkout --quiet --detach "$previous_sha"
    printf '%s\n' "$previous_override" > docker-compose.override.yml
    docker compose up -d --remove-orphans
  fi
  exit 1
}

# ghcr.io/<owner>/<repo> from this clone's GitHub remote (lowercase, as GHCR requires)
image_name() {
  local url path
  url="$(git config --get remote.origin.url)"
  path="${url#*github.com[:/]}"
  path="${path%.git}"
  if [[ ! "$path" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
    echo "unexpected git remote: $url" >&2
    exit 1
  fi
  echo "ghcr.io/${path,,}"
}

# The container must be running and not restarting 20 seconds after start
healthy() {
  sleep 20
  local state
  state="$(docker compose ps --format '{{.State}}' bot 2>/dev/null || true)"
  [[ "$state" == "running" ]]
}

main "$@"
