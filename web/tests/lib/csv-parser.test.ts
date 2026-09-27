import { describe, it, expect } from "vitest";
import { parseProcessCSV, CSVParseError } from "../../src/lib/csv-parser";

describe("CSV Parser", () => {
  it("should successfully parse standard CSV headers", () => {
    const csv = `Process Name,PID,CPU %,Memory (MB),Has Window,Signed,Path
explorer.exe,1234,1.5,85.2,Yes,Yes,C:\\Windows\\explorer.exe
svchost.exe,5678,0.2,22.1,No,Yes,C:\\Windows\\System32\\svchost.exe`;

    const rows = parseProcessCSV(csv);
    expect(rows).toHaveLength(2);
    expect(rows[0].name).toBe("explorer.exe");
    expect(rows[0].pid).toBe(1234);
    expect(rows[0].cpu).toBe(1.5);
    expect(rows[0].memoryMb).toBe(85.2);
    expect(rows[0].hasWindow).toBe(true);
    expect(rows[0].isSigned).toBe(true);
  });

  it("should normalize header aliases like 'ImageName' and 'ProcessId'", () => {
    const csv = `ImageName,ProcessId,CPU Usage,Working Set (Private)
Discord.exe,4421,2.0,180.5`;

    const rows = parseProcessCSV(csv);
    expect(rows).toHaveLength(1);
    expect(rows[0].name).toBe("Discord.exe");
    expect(rows[0].pid).toBe(4421);
    expect(rows[0].cpu).toBe(2.0);
    expect(rows[0].memoryMb).toBe(180.5);
  });

  it("should throw CSVParseError when required identifier column is missing", () => {
    const invalidCsv = `Col1,Col2,Col3\n1,2,3`;
    expect(() => parseProcessCSV(invalidCsv)).toThrow(CSVParseError);
  });

  it("should throw CSVParseError on empty string", () => {
    expect(() => parseProcessCSV("")).toThrow(CSVParseError);
  });
});
