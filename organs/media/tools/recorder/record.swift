// media-recorder — native macOS screen + SYSTEM AUDIO (+ optional mic) recorder.
//
// Carrier-Wave Media organ · capture front-end (Spine A intake).
//
// Uses ScreenCaptureKit's SCRecordingOutput (macOS 15+) so the Mac's *internal /
// system* audio is captured WITHOUT any virtual loopback driver (no BlackHole,
// no Loopback, no Multi-Output device). macOS's built-in ⇧⌘5 recorder can only
// capture a microphone; this closes that exact gap natively. See README.md.
//
// The muxed .mov is written into the existing capture location
// (~/Pictures/Screen Captures) by default, so the already-live screenshot
// importer + the media-ark archive pipeline pick it up automatically. Override
// with --out.
//
// Build:   ./build.sh        (runs swiftc; no external deps)
// Run:     ./media-recorder --seconds 10 [--out PATH] [--no-mic] [--display N]
//
// First run triggers a one-time macOS Screen-Recording (and Microphone) TCC
// grant — that GUI approval is the single human atom; everything else is
// scriptable. Lever: L-TCC-RECORDER.

import AVFoundation
import Foundation
import ScreenCaptureKit

struct Options {
    var seconds: Double = 10
    var out: String?
    var mic: Bool = true
    var displayIndex: Int = 0
}

func parseArgs() -> Options {
    var o = Options()
    let args = Array(CommandLine.arguments.dropFirst())
    var i = 0
    while i < args.count {
        let a = args[i]
        switch a {
        case "--seconds", "-s":
            i += 1
            if i < args.count, let v = Double(args[i]) { o.seconds = v }
        case "--out", "-o":
            i += 1
            if i < args.count { o.out = args[i] }
        case "--display", "-d":
            i += 1
            if i < args.count, let v = Int(args[i]) { o.displayIndex = v }
        case "--no-mic":
            o.mic = false
        case "--help", "-h":
            printUsage()
            exit(0)
        default:
            FileHandle.standardError.write(Data("media-recorder: unknown arg \(a)\n".utf8))
        }
        i += 1
    }
    return o
}

func printUsage() {
    let usage = """
    media-recorder — native screen + system-audio (+ mic) recorder (ScreenCaptureKit).

      --seconds, -s N   record N seconds (default 10)
      --out, -o PATH    output .mov (default ~/Pictures/Screen Captures/Recording-<ts>.mov)
      --display, -d N   display index (default 0 = main)
      --no-mic          system audio only (skip microphone)
      --help, -h        this help

    Captures SYSTEM audio natively — no BlackHole / virtual driver needed.
    First run prompts a one-time Screen Recording + Microphone permission (TCC).
    """
    print(usage)
}

func defaultOutputURL() -> URL {
    let dir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Pictures/Screen Captures", isDirectory: true)
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let fmt = DateFormatter()
    fmt.dateFormat = "yyyyMMdd-HHmmss"
    let ts = fmt.string(from: Date())
    return dir.appendingPathComponent("Recording-\(ts).mov")
}

@available(macOS 15.0, *)
final class Recorder: NSObject, SCStreamDelegate, SCRecordingOutputDelegate {
    private var finished: CheckedContinuation<Void, Never>?

    func run(_ opts: Options) async throws {
        let url = opts.out.map { URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath) }
            ?? defaultOutputURL()

        let content = try await SCShareableContent.excludingDesktopWindows(
            false, onScreenWindowsOnly: false)
        guard !content.displays.isEmpty else {
            throw RecorderError.noDisplay
        }
        let idx = min(max(opts.displayIndex, 0), content.displays.count - 1)
        let display = content.displays[idx]

        let filter = SCContentFilter(display: display, excludingWindows: [])

        let cfg = SCStreamConfiguration()
        cfg.capturesAudio = true            // <-- the Mac's system/internal audio
        cfg.captureMicrophone = opts.mic    // macOS 15+: mic as a second track
        cfg.width = display.width
        cfg.height = display.height
        cfg.showsCursor = true
        cfg.sampleRate = 48_000
        cfg.channelCount = 2

        let stream = SCStream(filter: filter, configuration: cfg, delegate: self)

        let recCfg = SCRecordingOutputConfiguration()
        recCfg.outputURL = url
        recCfg.outputFileType = .mov
        let recOutput = SCRecordingOutput(configuration: recCfg, delegate: self)
        try stream.addRecordingOutput(recOutput)

        let startMsg = "media-recorder: display \(idx) \(display.width)x\(display.height), "
            + "system-audio=on mic=\(opts.mic), \(opts.seconds)s -> \(url.path)\n"
        FileHandle.standardError.write(Data(startMsg.utf8))

        try await stream.startCapture()
        try await Task.sleep(nanoseconds: UInt64(opts.seconds * 1_000_000_000))
        try await stream.stopCapture()

        // Wait for the recording output to finalize the file before exiting.
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            self.finished = c
            // Safety timeout: resume after 5s even if the delegate never fires.
            DispatchQueue.global().asyncAfter(deadline: .now() + 5) { [weak self] in
                self?.resumeFinish()
            }
        }

        let attrs = try? FileManager.default.attributesOfItem(atPath: url.path)
        let size = (attrs?[.size] as? Int) ?? 0
        guard size > 0 else {
            throw RecorderError.emptyOutput(url.path)
        }
        print(url.path)
    }

    private func resumeFinish() {
        if let c = finished { finished = nil; c.resume() }
    }

    // MARK: - SCRecordingOutputDelegate
    func recordingOutputDidStartRecording(_ recordingOutput: SCRecordingOutput) {}

    func recordingOutput(_ recordingOutput: SCRecordingOutput, didFailWithError error: Error) {
        FileHandle.standardError.write(Data("media-recorder: recording failed: \(error)\n".utf8))
        resumeFinish()
    }

    func recordingOutputDidFinishRecording(_ recordingOutput: SCRecordingOutput) {
        resumeFinish()
    }

    // MARK: - SCStreamDelegate
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write(Data("media-recorder: stream stopped: \(error)\n".utf8))
        resumeFinish()
    }
}

enum RecorderError: Error, CustomStringConvertible {
    case noDisplay
    case emptyOutput(String)
    case unsupportedOS

    var description: String {
        switch self {
        case .noDisplay: return "no display available to capture"
        case .emptyOutput(let p): return "output file empty (permission denied?): \(p)"
        case .unsupportedOS: return "requires macOS 15 or newer (SCRecordingOutput)"
        }
    }
}

@main
struct Main {
    static func main() async {
        let opts = parseArgs()
        guard #available(macOS 15.0, *) else {
            FileHandle.standardError.write(Data("\(RecorderError.unsupportedOS)\n".utf8))
            exit(2)
        }
        do {
            try await Recorder().run(opts)
        } catch {
            FileHandle.standardError.write(Data("media-recorder: \(error)\n".utf8))
            exit(1)
        }
    }
}
