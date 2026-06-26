export default function Stamp({ size = 32, reversed }) {
  const src = reversed ? '/assets/mark-terroir-reversed.svg' : '/assets/mark-terroir.svg';
  return <img src={src} width={size} height={size} alt="Terroir" style={{ display: 'block' }} />;
}
