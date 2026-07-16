export function DataTable({
  title,
  columns,
  rows,
  emptyMessage,
}: {
  title: string;
  columns: string[];
  rows: unknown[];
  emptyMessage: string;
}) {
  if (rows.length === 0) {
    return (
      <div data-testid="dashboard-page-ready">
        <h1 className="mb-4 text-2xl font-semibold">{title}</h1>
        <p className="text-sm text-text-muted">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div data-testid="dashboard-page-ready">
      <h1 className="mb-4 text-2xl font-semibold">{title}</h1>
      <div className="overflow-x-auto rounded-xl border border-border-subtle">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-bg-elevated text-text-muted">
            <tr>
              {columns.map((column) => (
                <th key={column} className="px-3 py-2 font-medium">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-border-subtle">
                {columns.map((column) => {
                  const record = row as Record<string, unknown>;
                  return (
                    <td key={column} className="px-3 py-2 align-top">
                      {String(record[column] ?? "")}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
