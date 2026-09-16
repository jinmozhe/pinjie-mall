#!/usr/bin/env bash

set -euo pipefail

readonly EXPECTED_REGISTRY="ccr.ccs.tencentyun.com"
readonly EXPECTED_NAMESPACE="pinjie-mall"
readonly EXPECTED_SOURCE_REPOSITORY="https://github.com/jinmozhe/pinjie-mall"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Required environment variable $name is missing."
    exit 1
  fi
}

fail_validation() {
  echo "CNB release context validation failed: $1"
  exit 1
}

require_command() {
  local name="$1"
  command -v "$name" >/dev/null || fail_validation "required command $name is unavailable."
}

resolve_image() {
  case "${IMAGE_KEY:-}" in
    backend)
      IMAGE_DOCKERFILE="apps/backend/Dockerfile"
      IMAGE_NAME="pinjie-mall-backend"
      ;;
    admin)
      IMAGE_DOCKERFILE="apps/admin/Dockerfile"
      IMAGE_NAME="pinjie-mall-admin"
      ;;
    *)
      fail_validation "IMAGE_KEY must be one of backend or admin."
      ;;
  esac
}

candidate_tag() {
  printf 'candidate-%s' "$CNB_BUILD_ID"
}

write_source_metadata() {
  local commit_epoch
  local commit_time

  commit_epoch="$(git show -s --format=%ct "$CNB_COMMIT")"
  [[ "$commit_epoch" =~ ^[1-9][0-9]*$ ]] ||
    fail_validation "Git committer epoch must be a positive integer."
  commit_time="$(date -u --date="@$commit_epoch" '+%Y-%m-%dT%H:%M:%SZ')"
  [[ "$commit_time" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] ||
    fail_validation "Git committer time must normalize to UTC RFC 3339."

  printf '%s\n' "$commit_epoch" > "$EVIDENCE_ROOT/source-commit-epoch.txt"
  printf '%s\n' "$commit_time" > "$EVIDENCE_ROOT/source-commit-time.txt"
}

validate_context() {
  local name

  resolve_image
  for name in \
    CNB_BRANCH \
    CNB_BUILD_ID \
    CNB_BUILD_START_TIME \
    CNB_BUILD_WEB_URL \
    CNB_COMMIT \
    CNB_REPO_SLUG \
    DOCKER_CONFIG \
    EVIDENCE_ROOT \
    EXPECTED_CNB_BRANCH \
    EXPECTED_CNB_REPOSITORY \
    RELEASE_PIPELINE \
    TCR_NAMESPACE \
    TCR_PUBLISH_PASSWORD \
    TCR_PUBLISH_USERNAME \
    TCR_REGISTRY; do
    require_env "$name"
  done

  require_command bash
  require_command date
  require_command docker
  require_command git
  require_command jq

  [[ "$CNB_COMMIT" =~ ^[0-9a-f]{40}$ ]] ||
    fail_validation "CNB_COMMIT must be a full lowercase Git SHA."
  [[ "$CNB_BUILD_ID" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$ ]] ||
    fail_validation "CNB_BUILD_ID cannot be represented as a unique Docker tag."
  [[ "$CNB_REPO_SLUG" == "$EXPECTED_CNB_REPOSITORY" ]] ||
    fail_validation "repository does not match the approved CNB repository."
  [[ "$CNB_BRANCH" == "$EXPECTED_CNB_BRANCH" ]] ||
    fail_validation "branch does not match the approved release branch."
  [[ "$TCR_REGISTRY" == "$EXPECTED_REGISTRY" ]] ||
    fail_validation "TCR registry does not match the approved registry."
  [[ "$TCR_NAMESPACE" == "$EXPECTED_NAMESPACE" ]] ||
    fail_validation "TCR namespace does not match the approved namespace."
  [[ "$RELEASE_PIPELINE" == "$IMAGE_KEY-image" ]] ||
    fail_validation "release pipeline does not match IMAGE_KEY."
  [[ "$DOCKER_CONFIG" == "/tmp/pinjie-cnb-docker-config-$IMAGE_KEY" ]] ||
    fail_validation "Docker configuration path does not match IMAGE_KEY."
  [[ "$EVIDENCE_ROOT" == ".cnb/evidence/$IMAGE_KEY" ]] ||
    fail_validation "evidence path does not match IMAGE_KEY."
  [[ "$(git rev-parse HEAD)" == "$CNB_COMMIT" ]] ||
    fail_validation "checked-out Git SHA does not match CNB_COMMIT."

  docker buildx version || fail_validation "Docker Buildx is unavailable."

  mkdir -p "$DOCKER_CONFIG" "$EVIDENCE_ROOT"
  write_source_metadata
}

login_tcr() {
  printf '%s' "$TCR_PUBLISH_PASSWORD" |
    docker login "$TCR_REGISTRY" \
      --username "$TCR_PUBLISH_USERNAME" \
      --password-stdin >/dev/null
}

build_candidate() {
  local actual
  local candidate_ref
  local commit_epoch
  local commit_time
  local digest
  local image_config_file
  local image_index_file
  local image_ref
  local metadata_file

  validate_context
  login_tcr
  export BUILDX_METADATA_PROVENANCE=max
  export BUILDX_METADATA_WARNINGS=1
  commit_epoch="$(tr -d '\r\n' < "$EVIDENCE_ROOT/source-commit-epoch.txt")"
  commit_time="$(tr -d '\r\n' < "$EVIDENCE_ROOT/source-commit-time.txt")"
  export SOURCE_DATE_EPOCH="$commit_epoch"

  image_ref="$TCR_REGISTRY/$TCR_NAMESPACE/$IMAGE_NAME"
  candidate_ref="$image_ref:$(candidate_tag)"
  metadata_file="$EVIDENCE_ROOT/$IMAGE_KEY-metadata.json"
  image_index_file="$EVIDENCE_ROOT/$IMAGE_KEY-index.json"
  image_config_file="$EVIDENCE_ROOT/$IMAGE_KEY-image.json"

  if docker buildx imagetools inspect "$candidate_ref" >/dev/null 2>&1; then
    echo "Unique candidate tag $candidate_ref already exists."
    exit 1
  fi

  [[ -f "$IMAGE_DOCKERFILE" ]] ||
    fail_validation "Dockerfile for $IMAGE_KEY is missing."
  docker buildx build \
    --file "$IMAGE_DOCKERFILE" \
    --platform linux/amd64 \
    --provenance=mode=max \
    --sbom=true \
    --label "org.opencontainers.image.revision=$CNB_COMMIT" \
    --label "org.opencontainers.image.created=$commit_time" \
    --label "org.opencontainers.image.source=$EXPECTED_SOURCE_REPOSITORY" \
    --output "type=image,name=$candidate_ref,push=true,name-canonical=true" \
    --metadata-file "$metadata_file" \
    .

  digest="$(jq -er '."containerimage.digest"' "$metadata_file")" ||
    fail_validation "Build metadata does not contain containerimage.digest."
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] ||
    fail_validation "Build metadata digest has an invalid format."
  actual="$(docker buildx imagetools inspect "$candidate_ref" |
    awk '$1 == "Digest:" && !seen { print $2; seen=1 }')" ||
    fail_validation "Candidate registry inspection failed for $candidate_ref."
  [[ "$actual" == "$digest" ]] ||
    fail_validation "Candidate digest mismatch: metadata=$digest registry=$actual."
  jq -e \
    '(."buildx.build.provenance".buildType | type == "string" and length > 0)' \
    "$metadata_file" >/dev/null ||
    fail_validation "Build metadata is missing provenance buildType."

  docker buildx imagetools inspect "$image_ref@$digest" --raw > "$image_index_file" ||
    fail_validation "Registry manifest inspection failed for digest $digest."
  jq -e \
    '(.manifests | type == "array") and (.manifests | any(.annotations["vnd.docker.reference.type"] == "attestation-manifest"))' \
    "$image_index_file" >/dev/null ||
    fail_validation "Registry manifest is missing an attestation manifest."
  docker buildx imagetools inspect "$image_ref@$digest" \
    --format '{{json .Image}}' > "$image_config_file" ||
    fail_validation "Registry image config inspection failed for digest $digest."
  jq -e \
    --arg revision "$CNB_COMMIT" \
    --arg created "$commit_time" \
    --arg source "$EXPECTED_SOURCE_REPOSITORY" \
    '.config.Labels["org.opencontainers.image.revision"] == $revision and
     .config.Labels["org.opencontainers.image.created"] == $created and
     .config.Labels["org.opencontainers.image.source"] == $source' \
    "$image_config_file" >/dev/null ||
    fail_validation "Registry image labels do not match the requested source commit."
  printf '%s\n' "$digest" > "$EVIDENCE_ROOT/$IMAGE_KEY-digest.txt"
}

read_digest() {
  local digest
  local digest_file="$EVIDENCE_ROOT/$IMAGE_KEY-digest.txt"

  [[ -f "$digest_file" ]]
  digest="$(tr -d '\r\n' < "$digest_file")"
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
  printf '%s' "$digest"
}

finalize_tag() {
  local actual
  local digest
  local image_ref
  local target

  validate_context
  login_tcr
  digest="$(read_digest)"
  image_ref="$TCR_REGISTRY/$TCR_NAMESPACE/$IMAGE_NAME"
  target="$image_ref:sha-$CNB_COMMIT"
  actual="$(docker buildx imagetools inspect "$target" 2>/dev/null |
    awk '$1 == "Digest:" { print $2; exit }' || true)"
  if [[ -n "$actual" && "$actual" != "$digest" ]]; then
    echo "Immutable tag $target already points to $actual, expected $digest."
    exit 1
  fi

  if [[ -z "$actual" ]]; then
    docker buildx imagetools create --tag "$target" "$image_ref@$digest"
  fi
  actual="$(docker buildx imagetools inspect "$target" |
    awk '$1 == "Digest:" { print $2; exit }')"
  [[ "$actual" == "$digest" ]]
}

cleanup_credentials() {
  resolve_image
  [[ "${DOCKER_CONFIG:-}" == "/tmp/pinjie-cnb-docker-config-$IMAGE_KEY" ]] ||
    fail_validation "refusing to clean an unexpected Docker configuration path."
  if [[ -d "$DOCKER_CONFIG" ]]; then
    rm -rf -- "$DOCKER_CONFIG"
  fi
}

case "${1:-}" in
  validate)
    validate_context
    ;;
  build)
    build_candidate
    ;;
  finalize)
    finalize_tag
    ;;
  cleanup)
    cleanup_credentials
    ;;
  *)
    echo "Usage: $0 <validate|build|finalize|cleanup>"
    exit 2
    ;;
esac
