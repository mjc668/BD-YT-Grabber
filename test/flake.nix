{
  description = "Local example rendering for BD-YT-Grabber (no upload)";

  inputs.nixpkgs.url = "nixpkgs";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
      pythonEnv = pkgs: pkgs.python3.withPackages (ps: [ ps.faster-whisper ps.requests ]);
    in {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pythonEnv pkgs)
            pkgs.ffmpeg
            pkgs.yt-dlp
          ];
          shellHook = ''
            echo "Render example captions locally (nothing is uploaded):"
            echo "  python make_example.py <video-id-or-url> [...]"
          '';
        };
      });

      packages = forAllSystems (pkgs: {
        example = pkgs.writeShellApplication {
          name = "bd-yt-example";
          runtimeInputs = [ (pythonEnv pkgs) pkgs.ffmpeg pkgs.yt-dlp ];
          text = ''
            export BD_YT_REPO="''${BD_YT_REPO:-$PWD}"
            exec python ${./make_example.py} "$@"
          '';
        };
        default = self.packages.${pkgs.system}.example;
      });
    };
}
