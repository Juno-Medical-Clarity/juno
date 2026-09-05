import { Link } from 'react-router-dom';

export default function TermsPage() {
  return (
    <div className="legal-page">
      <Link to="/">← Back</Link>
      <article>{/* SP4's Terms & Conditions copy renders here */}</article>
    </div>
  );
}
