{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    python3Packages.pip
    python3Packages.requests
    python3Packages.faster-whisper
    ffmpeg
    yt-dlp
  ];
}
