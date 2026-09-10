{ pkgs, package }:
{
  package = package;
  integration =
    pkgs.runCommand "admaster-integration"
      {
        nativeBuildInputs = [
          package
          package.python
        ];
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        export ADMASTER_TEST_BIN=${package}/bin/admaster
        cp -r ${../tests} tests
        chmod -R u+w tests
        python tests/integration.py
        touch "$out"
      '';
}
