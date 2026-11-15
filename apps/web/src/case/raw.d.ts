// The staged listing is read as text for the story page (Vite's ?raw import).
declare module "*.txt?raw" {
  const text: string;
  export default text;
}
