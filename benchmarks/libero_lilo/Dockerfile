ARG PYTHON_IMAGE=python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b
FROM ${PYTHON_IMAGE}

ENV MUJOCO_GL=egl PYOPENGL_PLATFORM=egl PYTHONUNBUFFERED=1 \
    ROBORSI_LILO_COMMIT=64aa29d77f5457afb3d1642cfc84534dc1e81fad \
    ROBORSI_LIBERO_UPSTREAM_REF=f78abd68ee283de9f9be3c8f7e2a9ad60246e95c \
    ROBORSI_LIBERO_VERSION=lilo-64aa29d77f5457afb3d1642cfc84534dc1e81fad-libero-f78abd68ee283de9f9be3c8f7e2a9ad60246e95c
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make cmake libc6-dev linux-libc-dev libgl1 libegl1 libglib2.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --no-deps \
    'https://download.pytorch.org/whl/cpu/torch-2.2.0%2Bcpu-cp311-cp311-linux_x86_64.whl' \
    'https://download.pytorch.org/whl/cpu/torchvision-0.17.0%2Bcpu-cp311-cp311-linux_x86_64.whl'
RUN pip install --no-cache-dir \
    pydantic==2.11.7 jsonschema==4.23.0 pillow==11.3.0 imageio==2.37.0 \
    imageio-ffmpeg==0.6.0 numpy==1.26.4 scipy==1.15.3 pyyaml==6.0.2 \
    robosuite==1.4.1 mujoco==3.3.0 bddl==1.0.1 \
    robomimic==0.2.0 easydict==1.9 future==1.0.0 matplotlib==3.9.2 \
    cloudpickle==3.1.2 gym==0.25.2
ARG LIBERO_ARCHIVE_URL=https://codeload.github.com/Lifelong-Robot-Learning/LIBERO/tar.gz/f78abd68ee283de9f9be3c8f7e2a9ad60246e95c
ARG LIBERO_ARCHIVE_SHA256=0b0daa3659070f929d6032534d193b36b68acd7239b5a33bfc5472ba621ec18e
ADD ${LIBERO_ARCHIVE_URL} /tmp/libero.tar.gz
RUN echo "${LIBERO_ARCHIVE_SHA256}  /tmp/libero.tar.gz" | sha256sum -c - \
    && mkdir /opt/libero && tar -xzf /tmp/libero.tar.gz -C /opt/libero --strip-components=1 \
    && pip install --no-cache-dir --no-deps -e /opt/libero
ARG LILO_ARCHIVE_URL=https://codeload.github.com/YY-GX/LiLo-VLA/tar.gz/64aa29d77f5457afb3d1642cfc84534dc1e81fad
ARG LILO_ARCHIVE_SHA256=4ffd28a4c6090a41ce8b128a8b13d4317229fb0fe8c1b60f9aab90eed32df889
ADD ${LILO_ARCHIVE_URL} /tmp/lilo.tar.gz
RUN echo "${LILO_ARCHIVE_SHA256}  /tmp/lilo.tar.gz" | sha256sum -c - \
    && mkdir /opt/lilo-vla && tar -xzf /tmp/lilo.tar.gz -C /opt/lilo-vla --strip-components=1 \
    && mkdir -p /opt/lilo-vla/configs/libero \
    && pip install --no-cache-dir --no-deps -e /opt/lilo-vla

WORKDIR /opt/roborsi
COPY benchmark-runtime/ /opt/roborsi/
ENV PYTHONPATH=/opt/roborsi:/opt/lilo-vla:/opt/libero PYTHONDONTWRITEBYTECODE=1 \
    LIBERO_CONFIG_PATH=/tmp/libero-config MPLCONFIGDIR=/tmp/matplotlib NUMBA_CACHE_DIR=/tmp/numba \
    ROBORSI_LILO_ROOT=/opt/lilo-vla ROBORSI_LIBERO_BENCHMARK=libero_long_plus_plus \
    ROBORSI_LIBERO_ASSETS_ROOT=/opt/libero/libero/libero/assets \
    ROBORSI_LIBERO_BENCHMARK_ROOT=/opt/libero/libero/libero \
    ROBORSI_LIBERO_DATASETS_ROOT=/opt/libero/libero/datasets \
    ROBORSI_LIBERO_BDDL_ROOT=/opt/lilo-vla/configs/bddl \
    ROBORSI_LIBERO_INIT_ROOT=/opt/lilo-vla/configs/init_states
RUN python -B -c "from pathlib import Path; from roborsi.benchmarks.runtime_source import verify_benchmark_runtime; verify_benchmark_runtime(Path('/opt/roborsi'), 'libero_lilo')"
CMD ["python", "-m", "robots.libero.three_benchmark_serve", "--benchmark", "libero_long_plus_plus", "--profile", "official"]
