FROM python:3.13-slim AS build
WORKDIR /build
COPY pyproject.toml README.md constraints-dev.txt ./
COPY src ./src
RUN PIP_CONSTRAINT=constraints-dev.txt pip wheel --no-cache-dir . -w /wheels && \
    python -c "import glob,zipfile,collections,pathlib; w=glob.glob('/wheels/theme_candidate*.whl')[0]; n=zipfile.ZipFile(w).namelist(); s=[x for x in n if x.startswith('theme_compare/schemas/')]; c=collections.Counter(s); e={'theme_compare/schemas/'+p.name for p in pathlib.Path('src/theme_compare/schemas').iterdir() if p.is_file()}; assert set(s)==e and all(v==1 for v in c.values()), (c,e)"

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 THEME_COMPARE_STORAGE_ROOT=/data/sessions
RUN addgroup --system runtime && adduser --system --ingroup runtime runtime && mkdir -p /data/sessions && chown -R runtime:runtime /data
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
USER runtime
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["theme-compare", "serve", "--host", "0.0.0.0", "--port", "8000"]
