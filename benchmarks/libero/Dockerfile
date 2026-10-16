# Build the context exported by python -m benchmarks.package.
# CPU rendering keeps the environment runnable without a model or GPU.
ARG LIBERO_RUNTIME_IMAGE=python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b
FROM ${LIBERO_RUNTIME_IMAGE}

ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa LIBERO_TYPE=standard \
    PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    NUMBA_NUM_THREADS=1
# pynput pulls in evdev, whose Linux extension is built from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev linux-libc-dev libosmesa6 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/roborsi
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes -r /tmp/requirements.txt
# RLinf's environment modules do not need its training and distributed stack.
RUN pip install --no-cache-dir --no-deps \
    'https://files.pythonhosted.org/packages/cb/db/0d7849be4c5406e45d6126cca03a978e8a6cf146470148201c7064a0d411/rpent_rlinf-0.3.0-py3-none-any.whl#sha256=d86d4ebfd9dcb9dde26793f8cd43488ec66b3e4c173196f718beea8f2fec3d91'
ENV ROBORSI_LIBERO_COMMIT=a8323074d93a09e32bd898630a70531b1f51bc77
ADD --checksum=sha256:ea0e4f90840843743c69db07e8feccfaada1241fcf111a725a88d4581935775a \
    https://codeload.github.com/RLinf/LIBERO/tar.gz/${ROBORSI_LIBERO_COMMIT} /tmp/libero.tar.gz
RUN mkdir /opt/libero && tar -xzf /tmp/libero.tar.gz -C /opt/libero --strip-components=1 \
    && pip install --no-cache-dir --no-deps /opt/libero \
    && python -c "from pathlib import Path; import libero.libero as l; (Path(l.__file__).parent / 'assets').symlink_to('/roborsi/assets/libero')"

COPY benchmark-runtime/ /opt/roborsi/
ENV PYTHONPATH=/opt/roborsi PYTHONDONTWRITEBYTECODE=1 \
    LIBERO_CONFIG_PATH=/tmp/libero-config MPLCONFIGDIR=/tmp/matplotlib \
    NUMBA_CACHE_DIR=/tmp/numba
RUN python -B -c "from pathlib import Path; from roborsi.benchmarks.runtime_source import verify_benchmark_runtime; verify_benchmark_runtime(Path('/opt/roborsi'), 'libero')"
CMD ["python", "-m", "roborsi.evaluation.service_host", "--kind", "benchmark", "--factory", "robots.libero.benchmark_service:make_libero_benchmark", "--host", "0.0.0.0", "--port", "8000"]
