class Limen < Formula
  desc "Universal agent task intake — one file to aim every AI agent"
  homepage "https://github.com/4444J99/limen"
  url "https://github.com/4444J99/limen/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  depends_on "python@3.12"

  def install
    cd "cli" do
      system "python3", "-m", "pip", "install", "--prefix=#{prefix}", "-e", "."
    end
  end

  test do
    assert_match "limen", shell_output("#{bin}/limen --help")
  end
end
