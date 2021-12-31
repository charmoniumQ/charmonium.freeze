{
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        name = "charmonium-determ-hash";
        name-shell = "${name}-shell";
        name-test = "${name}-test";
        default-python = pkgs.python39;
        # Alternative Pythons for Tox
        alternative-pythons = [
          pkgs.python37
          pkgs.python38
          pkgs.python39
          pkgs.python310
          pkgs.pypy3
        ];
        poetry2nix-crypto-override = pkgs.poetry2nix.overrides.withDefaults (self: super: {
          cryptography = super.cryptography.overridePythonAttrs(old: {
            cargoDeps = pkgs.rustPlatform.fetchCargoTarball {
              inherit (old) src;
              name = "${old.pname}-${old.version}";
              sourceRoot = "${old.pname}-${old.version}/src/rust/";
              sha256 = "sha256-Y6TuW7AryVgSvZ6G8WNoDIvi+0tvx8ZlEYF5qB0jfNk=";
            };
            cargoRoot = "src/rust";
            nativeBuildInputs = old.nativeBuildInputs ++ (with pkgs.rustPlatform; [
              rust.rustc
              rust.cargo
              cargoSetupHook
            ]);
          });
        });
      in {
        packages.${name} = pkgs.poetry2nix.mkPoetryApplication {
          projectDir = ./.;
          python = default-python;
        };
        packages.${name-shell} = pkgs.mkShell {
          buildInputs = alternative-pythons ++ [
            pkgs.poetry
            # (pkgs.poetry2nix.mkPoetryEnv {
            #   projectDir = ./.;
            #   # default Python for shell
            #   python = default-python;
            #   overrides = poetry2nix-crypto-override;
            # })
          ];
          # TODO: write a check expression (`nix flake check`)
        };
        devShell = self.packages.${system}.${name-shell};
        defaultPackage = self.packages.${system}.${name};
      });
}
