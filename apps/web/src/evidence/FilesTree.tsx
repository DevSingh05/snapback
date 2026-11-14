export interface AgentFile {
  path: string;
  written_by: "code" | "agent";
}

interface Dir {
  name: string;
  files: AgentFile[];
}

function group(files: AgentFile[]): Dir[] {
  const dirs = new Map<string, AgentFile[]>();
  for (const f of files) {
    const cut = f.path.lastIndexOf("/");
    const dir = cut > 0 ? f.path.slice(0, cut) : "/";
    dirs.set(dir, [...(dirs.get(dir) ?? []), f]);
  }
  return [...dirs.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, list]) => ({ name, files: list }));
}

const base = (path: string) => path.slice(path.lastIndexOf("/") + 1);

// The agent's file system as a tree. Each file says who wrote it: code (numbers the card can
// read) or the agent (its own words, never on the card).
export function FilesTree({ files }: { files: AgentFile[] }) {
  if (files.length === 0)
    return (
      <p className="ft-empty" data-testid="files-empty">
        No files written yet.
      </p>
    );
  return (
    <ul className="ft" data-testid="files-tree" aria-label="Files the run wrote">
      {group(files).map((d) => (
        <li key={d.name} className="ft-dir">
          <span className="ft-dirname mono">{d.name}/</span>
          <ul className="ft-files">
            {d.files.map((f) => (
              <li key={f.path} className="ft-file" data-testid="files-file" data-by={f.written_by}>
                <span className="ft-name mono">{base(f.path)}</span>
                <span className={`ft-badge ft-badge-${f.written_by}`}>
                  {f.written_by === "code" ? "written by code" : "written by the agent"}
                </span>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}
