#!/bin/sh

set -eu

: "${EVIDENCE_ROOT:?EVIDENCE_ROOT is required}"
: "${IMAGE_KEY:?IMAGE_KEY is required}"
: "${TCR_NAMESPACE:?TCR_NAMESPACE is required}"
: "${TCR_PUBLISH_PASSWORD:?TCR_PUBLISH_PASSWORD is required}"
: "${TCR_PUBLISH_USERNAME:?TCR_PUBLISH_USERNAME is required}"
: "${TCR_REGISTRY:?TCR_REGISTRY is required}"

[ "$TCR_REGISTRY" = "ccr.ccs.tencentyun.com" ]
[ "$TCR_NAMESPACE" = "pinjie-mall" ]
[ "$EVIDENCE_ROOT" = ".cnb/evidence/$IMAGE_KEY" ]

case "$IMAGE_KEY" in
  backend) image_name="pinjie-mall-backend" ;;
  admin) image_name="pinjie-mall-admin" ;;
  *)
    echo "IMAGE_KEY must be one of backend or admin."
    exit 1
    ;;
esac

export TRIVY_USERNAME="$TCR_PUBLISH_USERNAME"
export TRIVY_PASSWORD="$TCR_PUBLISH_PASSWORD"

failure_summary="$EVIDENCE_ROOT/scan-failure-summary.txt"
rm -f "$failure_summary"

write_scan_failure() {
  image_ref="$1"
  phase="$2"
  report_file="${3:-}"

  {
    printf 'image=%s\n' "$IMAGE_KEY"
    printf 'reference=%s\n' "$image_ref"
    printf 'phase=%s\n' "$phase"
    if [ -n "$report_file" ] && [ -s "$report_file" ]; then
      printf '\n'
      cat "$report_file"
    fi
  } > "$failure_summary"

  cat "$failure_summary"
}

digest_file="$EVIDENCE_ROOT/$IMAGE_KEY-digest.txt"
json_report="$EVIDENCE_ROOT/$IMAGE_KEY-trivy-full.json"
table_report="$EVIDENCE_ROOT/$IMAGE_KEY-trivy-table.txt"
digest="$(tr -d '\r\n' < "$digest_file")"
if ! printf '%s' "$digest" | grep -Eq '^sha256:[0-9a-f]{64}$'; then
  echo "Invalid digest evidence for $IMAGE_KEY."
  exit 1
fi

image_ref="$TCR_REGISTRY/$TCR_NAMESPACE/$image_name@$digest"
if ! trivy image \
    --cache-dir /root/.cache/trivy \
    --timeout 20m \
    --exit-code 0 \
    --list-all-pkgs \
    --ignorefile /dev/null \
    --scanners vuln \
    --format json \
    --output "$json_report" \
    "$image_ref"; then
  write_scan_failure "$image_ref" "json-scan-error"
  exit 1
fi

if trivy convert \
    --exit-code 0 \
    --severity HIGH,CRITICAL \
    --scanners vuln \
    --format table \
    --output "$table_report" \
    "$json_report"; then
  test -s "$table_report"
else
  scan_status="$?"
  write_scan_failure "$image_ref" "blocking-vulnerability-or-scan-error" "$table_report"
  exit "$scan_status"
fi

if ! trivy convert \
  --format cyclonedx \
  --output "$EVIDENCE_ROOT/$IMAGE_KEY-sbom.cdx.json" \
  "$json_report"; then
  write_scan_failure "$image_ref" "sbom-conversion-error"
  exit 1
fi

test -s "$json_report"
test -s "$EVIDENCE_ROOT/$IMAGE_KEY-sbom.cdx.json"
