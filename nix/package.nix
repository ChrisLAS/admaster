{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  ffmpeg,
  reaper,
  xvfb-run,
  xauth,
  coreutils,
  lua5_4,
  ruff,
  shellcheck,
}:
let
  python = python3.withPackages (p: [
    p.numpy
    p.soundfile
  ]);
  runtime = [
    ffmpeg
    reaper
    xvfb-run
    xauth
    coreutils
  ];
in
stdenvNoCC.mkDerivation {
  pname = "admaster";
  version = "0.1.0";
  src = lib.cleanSource ../.;
  nativeBuildInputs = [
    makeWrapper
    python
    lua5_4
    ruff
    shellcheck
  ]
  ++ runtime;
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    export ADMASTER_ROOT="$PWD"
    python -m unittest discover -s tests -v
    ruff check admaster tests examples
    ruff format --check admaster tests examples
    shellcheck bin/admaster scripts/*
    for script in reaper/*.lua reaper/lib/*.lua; do luac -p "$script"; done
  '';
  installPhase = ''
    mkdir -p "$out/share/admaster" "$out/bin"
    cp -r admaster profiles reaper "$out/share/admaster/"
    makeWrapper ${python}/bin/python3 "$out/bin/admaster" \
      --add-flags '-m admaster' \
      --set PYTHONPATH "$out/share/admaster" \
      --set ADMASTER_ROOT "$out/share/admaster" \
      --prefix PATH : ${lib.makeBinPath runtime}
  '';
  passthru = { inherit python; };
  meta = {
    description = "Validated, natural-speed podcast ad mastering in REAPER";
    mainProgram = "admaster";
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    license = lib.licenses.unfree;
  };
}
