type Product = {
  id: number;
  name: string;
  photo_url: string;
};

async function getProducts(): Promise<Product[]> {
  const base = process.env.API_BASE_URL ?? "http://localhost:8010";
  try {
    const res = await fetch(`${base}/api/products`, { cache: "no-store" });
    if (!res.ok) return [];
    const data: { items: Product[] } = await res.json();
    return data.items;
  } catch {
    return [];
  }
}

export const dynamic = "force-dynamic";

export default async function CatalogPage() {
  const products = await getProducts();

  return (
    <main className="catalog">
      <h1>Каталог</h1>
      {products.length === 0 ? (
        <p className="empty">Товаров пока нет. Создайте первый через бота.</p>
      ) : (
        <ul className="grid">
          {products.map((p) => (
            <li key={p.id} className="card">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.photo_url} alt={p.name} loading="lazy" />
              <span className="name">{p.name}</span>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
