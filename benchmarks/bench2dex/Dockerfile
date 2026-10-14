# Export with python -m benchmarks.package after framework source registration.
# The pinned NVIDIA base owns Isaac Sim. Assets are mounted separately.
ARG ISAAC_SIM_BASE=nvcr.io/nvidia/isaac-sim@sha256:93b0f99635ab126fb5b33298d513c11520f119f0ee60ff8414ccef67ea977829
FROM ${ISAAC_SIM_BASE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/native
RUN git clone https://github.com/Bench2Dex/Bench2Dex.git Bench2Dex \
    && git -C Bench2Dex checkout f96a8b2b4eb475483af66e9e03916b35bc43f1be \
    && git clone https://github.com/isaac-sim/IsaacLab.git IsaacLab \
    && git -C IsaacLab checkout 37ddf626871758333d6ed89cf64ad702aef127d0 \
    && ln -s /roborsi/assets/bench2dex /opt/native/dex2bench_dataset
COPY native-requirements.txt /opt/build/native-requirements.txt
COPY native-environment.lock.txt /opt/build/native-environment.lock.txt
# Constraints retain the tested host's relevant dependency versions. The complete
# resolved image lock is captured by build.py and must pass clean/GPU validation.
RUN /isaac-sim/python.sh -m pip install --extra-index-url https://download.pytorch.org/whl/cu128 \
    -c /opt/build/native-environment.lock.txt -r /opt/build/native-requirements.txt \
    -e /opt/native/IsaacLab/source/isaaclab \
    && /isaac-sim/python.sh -m pip check
COPY python-runtime.sh /opt/bench2dex/bin/python
RUN chmod 755 /opt/bench2dex/bin/python
ENV PATH=/opt/bench2dex/bin:${PATH} \
    PYTHONPATH=/opt/roborsi \
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 \
    BENCH2DEX_ROOT=/opt/native/Bench2Dex ISAACLAB_ROOT=/opt/native/IsaacLab \
    ISAACLAB_PYTHON=/opt/bench2dex/bin/python \
    BENCH2DEX_ASSETS=/roborsi/assets/bench2dex \
    BENCH2DEX_CATALOG=/roborsi/assets/bench2dex-catalog \
    HOME=/tmp XDG_CACHE_HOME=/tmp/cache MPLCONFIGDIR=/tmp/matplotlib \
    TORCH_EXTENSIONS_DIR=/tmp/torch-extensions WARP_CACHE_PATH=/tmp/warp \
    NVIDIA_DRIVER_CAPABILITIES=all
WORKDIR /opt/roborsi
COPY benchmark-runtime/ /opt/roborsi/
RUN python -P -c "from pathlib import Path; from roborsi.benchmarks.runtime_source import verify_benchmark_runtime; verify_benchmark_runtime(Path('/opt/roborsi'),'bench2dex')"
ENTRYPOINT []
CMD ["python", "-P", "-m", "roborsi.evaluation.service_host", "--kind", "benchmark", "--factory", "robots.bench2dex.benchmark_service:make_bench2dex_benchmark", "--host", "0.0.0.0", "--port", "8000"]
