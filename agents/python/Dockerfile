# A Python Agent runtime without simulator dependencies.
FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b AS runtime
ARG AGENT_REQUIREMENTS=agents/python/requirements.txt
COPY ${AGENT_REQUIREMENTS} /tmp/requirements.txt
RUN pip install --require-hashes -r /tmp/requirements.txt
WORKDIR /opt/roborsi
COPY pyproject.toml README.md LICENSE ./
COPY roborsi ./roborsi
RUN pip install --no-build-isolation --no-deps .
ENV PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
CMD ["python", "-I", "-B", "-m", "roborsi.evaluation.service_host", "--help"]

# Build with --target configured and a lock containing the selected Agent's deps.
FROM runtime AS configured
ARG AGENT_WHEEL
COPY ${AGENT_WHEEL} /tmp/agent-wheels/
RUN pip install --no-deps /tmp/agent-wheels/*.whl && pip check

# Preserve the existing default fixed-action image.
FROM runtime AS example
COPY examples/roborsi/hold_agent.py /usr/local/lib/python3.11/site-packages/roborsi_hold_agent.py
