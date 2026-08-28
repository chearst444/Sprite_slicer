/**
 * zip-writer.js
 * ---------------------------------------------------------------------
 * A tiny, dependency-free ZIP file writer.
 *
 * Sprite Sheet Splitter bundles its exported PNGs into a single .zip for
 * download. Rather than pull in a third-party library (and the network
 * dependency that comes with it), this file implements just enough of the
 * ZIP format — the STORED (uncompressed) method — to build a valid archive
 * that every major unzip tool and OS can open. PNG/JPEG data is already
 * compressed, so skipping DEFLATE costs almost nothing in file size while
 * keeping this file small and entirely self-contained.
 *
 * Usage:
 *   const blob = createZipBlob([{ name: "sprite_001.png", data: uint8Array }, ...]);
 *
 * Works in any modern browser (no build step) and under Node for testing.
 */
(function (global) {
  "use strict";

  // Precompute the standard CRC-32 lookup table (IEEE 802.3 polynomial).
  const CRC_TABLE = (() => {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) {
        c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      }
      table[n] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes) {
    let crc = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) {
      crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  // DOS date/time encoding used by the ZIP format (local time, 2-second
  // resolution). A fixed timestamp is fine here — sprite exports don't need
  // meaningful mtimes, and it keeps output deterministic for testing.
  function dosDateTime(date) {
    const time =
      ((date.getHours() & 0x1f) << 11) |
      ((date.getMinutes() & 0x3f) << 5) |
      ((date.getSeconds() >> 1) & 0x1f);
    const dosDate =
      (((date.getFullYear() - 1980) & 0x7f) << 9) |
      (((date.getMonth() + 1) & 0xf) << 5) |
      (date.getDate() & 0x1f);
    return { time, dosDate };
  }

  function utf8Bytes(str) {
    return new TextEncoder().encode(str);
  }

  function u16(v) {
    return [v & 0xff, (v >> 8) & 0xff];
  }
  function u32(v) {
    return [v & 0xff, (v >> 8) & 0xff, (v >> 16) & 0xff, (v >> 24) & 0xff];
  }

  /**
   * @param {Array<{name: string, data: Uint8Array}>} files
   * @returns {Uint8Array} the raw bytes of a valid .zip archive
   */
  function createZipBytes(files) {
    const now = new Date();
    const { time, dosDate } = dosDateTime(now);

    const localParts = [];
    const centralParts = [];
    let offset = 0;

    for (const file of files) {
      const nameBytes = utf8Bytes(file.name);
      const data = file.data;
      const crc = crc32(data);
      const size = data.length;

      // General purpose flag bit 11 (0x0800) marks the filename as UTF-8.
      const flag = 0x0800;
      const method = 0; // stored (no compression)

      const localHeader = new Uint8Array([
        0x50, 0x4b, 0x03, 0x04, // local file header signature
        ...u16(20), // version needed to extract
        ...u16(flag),
        ...u16(method),
        ...u16(time),
        ...u16(dosDate),
        ...u32(crc),
        ...u32(size), // compressed size
        ...u32(size), // uncompressed size
        ...u16(nameBytes.length),
        ...u16(0), // extra field length
      ]);

      localParts.push(localHeader, nameBytes, data);

      const centralHeader = new Uint8Array([
        0x50, 0x4b, 0x01, 0x02, // central directory header signature
        ...u16(20), // version made by
        ...u16(20), // version needed to extract
        ...u16(flag),
        ...u16(method),
        ...u16(time),
        ...u16(dosDate),
        ...u32(crc),
        ...u32(size),
        ...u32(size),
        ...u16(nameBytes.length),
        ...u16(0), // extra field length
        ...u16(0), // file comment length
        ...u16(0), // disk number start
        ...u16(0), // internal file attributes
        ...u32(0), // external file attributes
        ...u32(offset), // relative offset of local header
      ]);
      centralParts.push(centralHeader, nameBytes);

      offset += localHeader.length + nameBytes.length + data.length;
    }

    const centralStart = offset;
    let centralSize = 0;
    for (const part of centralParts) centralSize += part.length;

    const eocd = new Uint8Array([
      0x50, 0x4b, 0x05, 0x06, // end of central directory signature
      ...u16(0), // disk number
      ...u16(0), // disk with central directory
      ...u16(files.length), // entries on this disk
      ...u16(files.length), // total entries
      ...u32(centralSize),
      ...u32(centralStart),
      ...u16(0), // comment length
    ]);

    const allParts = [...localParts, ...centralParts, eocd];
    let total = 0;
    for (const part of allParts) total += part.length;

    const out = new Uint8Array(total);
    let pos = 0;
    for (const part of allParts) {
      out.set(part, pos);
      pos += part.length;
    }
    return out;
  }

  function createZipBlob(files) {
    return new Blob([createZipBytes(files)], { type: "application/zip" });
  }

  const api = { createZipBytes, createZipBlob, crc32 };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    global.ZipWriter = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
