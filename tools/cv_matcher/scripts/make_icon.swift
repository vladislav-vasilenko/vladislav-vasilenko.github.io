// Draws the Dock icon: the service's ↗ mark on its dark green. Usage: swift make_icon.swift out.png
import AppKit
import Foundation

let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
NSColor(calibratedRed: 0.09, green: 0.21, blue: 0.17, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 100, y: 100, width: 824, height: 824), xRadius: 186, yRadius: 186).fill()
NSColor(calibratedRed: 0.84, green: 0.93, blue: 0.82, alpha: 1).setStroke()
let arrow = NSBezierPath()
arrow.lineWidth = 72
arrow.lineCapStyle = .round
arrow.lineJoinStyle = .round
arrow.move(to: NSPoint(x: 330, y: 330))
arrow.line(to: NSPoint(x: 694, y: 694))
arrow.move(to: NSPoint(x: 380, y: 694))
arrow.line(to: NSPoint(x: 694, y: 694))
arrow.line(to: NSPoint(x: 694, y: 380))
arrow.stroke()
image.unlockFocus()
let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
