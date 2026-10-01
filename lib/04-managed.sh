#!/usr/bin/env bash

log 'Writing root-owned Hermes managed scope'
install -d -m 0755 -o root -g root /etc/hermes
case $MODEL_PROVIDER in
  openai-codex|opencode-zen) hermes_model_provider=$MODEL_PROVIDER ;;
  openai-compatible) hermes_model_provider=custom ;;
  *) echo 'MODEL_PROVIDER must be openai-codex, opencode-zen, or openai-compatible.' >&2; exit 1 ;;
esac
install -m 0644 "$KIT_DIR/managed/config.yaml" /etc/hermes/config.yaml
sed -i "s/^  provider: .*/  provider: $hermes_model_provider/" /etc/hermes/config.yaml
chown root:root /etc/hermes/config.yaml
chmod 0644 /etc/hermes/config.yaml
if [[ -n ${OTLP_HEALTH_ENDPOINT:-} ]]; then
  [[ $OTLP_HEALTH_ENDPOINT == https://* ]] || { echo 'OTLP_HEALTH_ENDPOINT must use HTTPS.' >&2; exit 1; }
  cat >> /etc/hermes/config.yaml <<EOF
monitoring:
  gateway_health_export:
    enabled: true
  export:
    otlp:
      enabled: true
      endpoint: $OTLP_HEALTH_ENDPOINT
      headers_env: {}
EOF
fi
