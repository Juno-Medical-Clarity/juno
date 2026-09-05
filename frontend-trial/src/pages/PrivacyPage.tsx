import { Link } from 'react-router-dom';

export default function PrivacyPage() {
  return (
    <div className="legal-page">
      <Link to="/">← Back</Link>
      <article>{/* SP4's Privacy Policy copy renders here */}</article>
    </div>
  );
}
