# Requires the framework-owned DexJoCo runtime source registration first.
# Build only the context produced by python -m benchmarks.package.
ARG DEXJOCO_BASE_IMAGE
FROM ${DEXJOCO_BASE_IMAGE}
ARG DEXJOCO_COMMIT=8d23b0fab23b17a58c4b55f3942e17013aaf8267
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    ROBORSI_DEXJOCO_UPSTREAM=/opt/dexjoco ROBORSI_DEXJOCO_MULTIPLIER=10
RUN apt-get update && apt-get install -y --no-install-recommends \
    git libosmesa6 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes -r /tmp/requirements.txt
RUN git clone https://github.com/brave-eai/dexjoco.git /opt/dexjoco \
    && git -C /opt/dexjoco checkout ${DEXJOCO_COMMIT} \
    && test "$(git -C /opt/dexjoco rev-parse HEAD)" = "${DEXJOCO_COMMIT}"
WORKDIR /opt/roborsi
COPY benchmark-runtime/ /opt/roborsi/
ENV PYTHONPATH=/opt/roborsi
RUN python -B -c "from pathlib import Path; from roborsi.benchmarks.runtime_source import verify_benchmark_runtime; verify_benchmark_runtime(Path('/opt/roborsi'), 'dexjoco')"
CMD ["python", "-m", "roborsi.evaluation.service_host", "--kind", "benchmark", "--factory", "robots.dexjoco.benchmark_service:make_dexjoco_benchmark", "--host", "0.0.0.0", "--port", "8000"]
