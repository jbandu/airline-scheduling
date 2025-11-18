"""
Validation Report Generator
Generates formatted validation reports
"""

from typing import List, Dict, Any
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates validation reports in multiple formats

    Formats:
    - JSON: Machine-readable format for API responses
    - Markdown: Human-readable format for documentation
    - HTML: Web-friendly format with styling
    - CSV: Tabular format for spreadsheet import
    """

    def generate_report(
        self,
        validation_state: Dict[str, Any],
        format: str = "json"
    ) -> str:
        """
        Generate validation report in specified format

        Args:
            validation_state: Complete validation state with all results
            format: Output format (json, markdown, html, csv)

        Returns:
            Formatted report string
        """
        if format == "json":
            return self._generate_json_report(validation_state)
        elif format == "markdown":
            return self._generate_markdown_report(validation_state)
        elif format == "html":
            return self._generate_html_report(validation_state)
        elif format == "csv":
            return self._generate_csv_report(validation_state)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_json_report(self, state: Dict[str, Any]) -> str:
        """Generate JSON report"""
        report = {
            "schedule_id": state.get("schedule_id"),
            "validation_timestamp": datetime.utcnow().isoformat(),
            "status": "completed" if state.get("validation_complete") else "in_progress",
            "statistics": {
                "total_flights": state.get("total_flights", 0),
                "total_issues": len(state.get("all_issues", [])),
                "critical_issues": len([i for i in state.get("all_issues", []) if i.get("severity") == "critical"]),
                "high_issues": len([i for i in state.get("all_issues", []) if i.get("severity") == "high"]),
                "medium_issues": len([i for i in state.get("all_issues", []) if i.get("severity") == "medium"]),
                "low_issues": len([i for i in state.get("all_issues", []) if i.get("severity") == "low"])
            },
            "validation_results": {
                "slot_validation": {
                    "status": "completed" if state.get("slot_validation_complete") else "pending",
                    "issues": state.get("slot_issues", [])
                },
                "aircraft_validation": {
                    "status": "completed" if state.get("aircraft_validation_complete") else "pending",
                    "issues": state.get("aircraft_issues", [])
                },
                "crew_validation": {
                    "status": "completed" if state.get("crew_validation_complete") else "pending",
                    "issues": state.get("crew_issues", [])
                },
                "mct_validation": {
                    "status": "completed" if state.get("mct_validation_complete") else "pending",
                    "issues": state.get("mct_issues", [])
                },
                "curfew_validation": {
                    "status": "completed" if state.get("curfew_validation_complete") else "pending",
                    "issues": state.get("curfew_issues", [])
                },
                "regulatory_validation": {
                    "status": "completed" if state.get("regulatory_validation_complete") else "pending",
                    "issues": state.get("regulatory_issues", [])
                },
                "routing_validation": {
                    "status": "completed" if state.get("routing_validation_complete") else "pending",
                    "issues": state.get("routing_issues", [])
                },
                "pattern_validation": {
                    "status": "completed" if state.get("pattern_validation_complete") else "pending",
                    "issues": state.get("pattern_issues", [])
                }
            },
            "analysis": state.get("analysis_result", {}),
            "recommendations": state.get("analysis_result", {}).get("recommendations", [])
        }

        return json.dumps(report, indent=2)

    def _generate_markdown_report(self, state: Dict[str, Any]) -> str:
        """Generate Markdown report"""
        issues = state.get("all_issues", [])
        analysis = state.get("analysis_result", {})

        critical = [i for i in issues if i.get("severity") == "critical"]
        high = [i for i in issues if i.get("severity") == "high"]
        medium = [i for i in issues if i.get("severity") == "medium"]
        low = [i for i in issues if i.get("severity") == "low"]

        md = f"""# Schedule Validation Report

**Schedule ID:** {state.get('schedule_id', 'N/A')}
**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
**Total Flights:** {state.get('total_flights', 0)}

---

## Executive Summary

{analysis.get('summary', 'No summary available')}

### Issue Statistics

| Severity | Count |
|----------|-------|
| Critical | {len(critical)} |
| High | {len(high)} |
| Medium | {len(medium)} |
| Low | {len(low)} |
| **Total** | **{len(issues)}** |

---

## Critical Issues

"""
        if critical:
            for i, issue in enumerate(critical, 1):
                md += f"""### {i}. {issue.get('issue_type', 'Unknown Issue')}

**Flight:** {issue.get('flight_number', 'N/A')}
**Category:** {issue.get('category', 'N/A')}
**Description:** {issue.get('description', 'No description')}

**Impact:** {issue.get('impact', 'No impact assessment')}

**Recommended Action:**
{issue.get('recommended_action', 'No recommendation')}

---

"""
        else:
            md += "*No critical issues found.*\n\n"

        md += f"""## High Priority Issues

"""
        if high:
            for i, issue in enumerate(high[:10], 1):  # Limit to 10 for brevity
                md += f"""### {i}. {issue.get('issue_type', 'Unknown')} - Flight {issue.get('flight_number', 'N/A')}

**Description:** {issue.get('description', 'No description')}
**Action:** {issue.get('recommended_action', 'No recommendation')}

"""
            if len(high) > 10:
                md += f"\n*... and {len(high) - 10} more high-priority issues.*\n"
        else:
            md += "*No high-priority issues found.*\n"

        md += f"""

---

## Root Cause Analysis

"""
        root_causes = analysis.get('root_causes', [])
        if root_causes:
            for rc in root_causes:
                md += f"""### {rc.get('cause', 'Unknown Cause')}

{rc.get('description', 'No description')}

**Affected Issues:** {rc.get('affected_issues', 0)}
**Recommended Fix:** {rc.get('recommended_fix', 'No recommendation')}

"""
        else:
            md += "*No root causes identified.*\n"

        md += f"""

---

## Recommendations

"""
        recommendations = analysis.get('recommendations', [])
        if recommendations:
            for rec in recommendations:
                md += f"""### {rec.get('title', 'Recommendation')}

**Priority:** {rec.get('priority', 'N/A').upper()}
**Timeline:** {rec.get('timeline', 'N/A')}

{rec.get('description', 'No description')}

**Actions:**
"""
                for action in rec.get('actions', []):
                    md += f"- {action}\n"

                md += "\n"
        else:
            md += "*No recommendations.*\n"

        md += f"""

---

## Validation Details

| Category | Issues Found | Status |
|----------|--------------|--------|
| Slot Validation | {len(state.get('slot_issues', []))} | {'✓' if state.get('slot_validation_complete') else '...'} |
| Aircraft Validation | {len(state.get('aircraft_issues', []))} | {'✓' if state.get('aircraft_validation_complete') else '...'} |
| Crew Validation | {len(state.get('crew_issues', []))} | {'✓' if state.get('crew_validation_complete') else '...'} |
| MCT Validation | {len(state.get('mct_issues', []))} | {'✓' if state.get('mct_validation_complete') else '...'} |
| Curfew Validation | {len(state.get('curfew_issues', []))} | {'✓' if state.get('curfew_validation_complete') else '...'} |
| Regulatory Validation | {len(state.get('regulatory_issues', []))} | {'✓' if state.get('regulatory_validation_complete') else '...'} |
| Routing Validation | {len(state.get('routing_issues', []))} | {'✓' if state.get('routing_validation_complete') else '...'} |
| Pattern Validation | {len(state.get('pattern_issues', []))} | {'✓' if state.get('pattern_validation_complete') else '...'} |

---

*Report generated by Schedule Validation Agent*
"""

        return md

    def _generate_html_report(self, state: Dict[str, Any]) -> str:
        """Generate HTML report"""
        issues = state.get("all_issues", [])
        analysis = state.get("analysis_result", {})

        critical = len([i for i in issues if i.get("severity") == "critical"])
        high = len([i for i in issues if i.get("severity") == "high"])
        medium = len([i for i in issues if i.get("severity") == "medium"])
        low = len([i for i in issues if i.get("severity") == "low"])

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Schedule Validation Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
        }}
        .summary {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .stat-box {{
            display: inline-block;
            margin: 10px;
            padding: 15px 25px;
            border-radius: 5px;
            min-width: 100px;
            text-align: center;
        }}
        .critical {{ background: #dc3545; color: white; }}
        .high {{ background: #fd7e14; color: white; }}
        .medium {{ background: #ffc107; color: #333; }}
        .low {{ background: #28a745; color: white; }}
        .issue-card {{
            border-left: 4px solid #007bff;
            padding: 15px;
            margin: 15px 0;
            background: #f8f9fa;
            border-radius: 4px;
        }}
        .issue-card.critical {{ border-left-color: #dc3545; }}
        .issue-card.high {{ border-left-color: #fd7e14; }}
        .issue-card.medium {{ border-left-color: #ffc107; }}
        .issue-card.low {{ border-left-color: #28a745; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #007bff;
            color: white;
        }}
        .recommendation {{
            background: #e7f3ff;
            padding: 15px;
            margin: 10px 0;
            border-left: 4px solid #007bff;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Schedule Validation Report</h1>

        <div class="summary">
            <p><strong>Schedule ID:</strong> {state.get('schedule_id', 'N/A')}</p>
            <p><strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <p><strong>Total Flights:</strong> {state.get('total_flights', 0)}</p>
        </div>

        <h2>Issue Summary</h2>
        <div style="text-align: center;">
            <div class="stat-box critical">
                <div style="font-size: 32px; font-weight: bold;">{critical}</div>
                <div>Critical</div>
            </div>
            <div class="stat-box high">
                <div style="font-size: 32px; font-weight: bold;">{high}</div>
                <div>High</div>
            </div>
            <div class="stat-box medium">
                <div style="font-size: 32px; font-weight: bold;">{medium}</div>
                <div>Medium</div>
            </div>
            <div class="stat-box low">
                <div style="font-size: 32px; font-weight: bold;">{low}</div>
                <div>Low</div>
            </div>
        </div>

        <h2>Executive Summary</h2>
        <div class="summary">
            {analysis.get('summary', 'No summary available').replace(chr(10), '<br>')}
        </div>

        <h2>Critical Issues</h2>
"""

        critical_issues = [i for i in issues if i.get("severity") == "critical"]
        if critical_issues:
            for issue in critical_issues:
                html += f"""
        <div class="issue-card critical">
            <h3>{issue.get('issue_type', 'Unknown Issue')}</h3>
            <p><strong>Flight:</strong> {issue.get('flight_number', 'N/A')}</p>
            <p><strong>Description:</strong> {issue.get('description', 'No description')}</p>
            <p><strong>Impact:</strong> {issue.get('impact', 'No impact assessment')}</p>
            <p><strong>Recommended Action:</strong> {issue.get('recommended_action', 'No recommendation')}</p>
        </div>
"""
        else:
            html += "<p>No critical issues found.</p>"

        html += """
        <h2>Recommendations</h2>
"""

        recommendations = analysis.get('recommendations', [])
        if recommendations:
            for rec in recommendations:
                html += f"""
        <div class="recommendation">
            <h3>{rec.get('title', 'Recommendation')}</h3>
            <p><strong>Priority:</strong> {rec.get('priority', 'N/A').upper()}</p>
            <p><strong>Timeline:</strong> {rec.get('timeline', 'N/A')}</p>
            <p>{rec.get('description', 'No description')}</p>
            <p><strong>Actions:</strong></p>
            <ul>
"""
                for action in rec.get('actions', []):
                    html += f"<li>{action}</li>"

                html += """
            </ul>
        </div>
"""
        else:
            html += "<p>No recommendations.</p>"

        html += f"""
        <h2>Validation Details</h2>
        <table>
            <tr>
                <th>Category</th>
                <th>Issues Found</th>
                <th>Status</th>
            </tr>
            <tr>
                <td>Slot Validation</td>
                <td>{len(state.get('slot_issues', []))}</td>
                <td>{'✓ Complete' if state.get('slot_validation_complete') else '⏳ Pending'}</td>
            </tr>
            <tr>
                <td>Aircraft Validation</td>
                <td>{len(state.get('aircraft_issues', []))}</td>
                <td>{'✓ Complete' if state.get('aircraft_validation_complete') else '⏳ Pending'}</td>
            </tr>
            <tr>
                <td>Crew Validation</td>
                <td>{len(state.get('crew_issues', []))}</td>
                <td>{'✓ Complete' if state.get('crew_validation_complete') else '⏳ Pending'}</td>
            </tr>
            <tr>
                <td>MCT Validation</td>
                <td>{len(state.get('mct_issues', []))}</td>
                <td>{'✓ Complete' if state.get('mct_validation_complete') else '⏳ Pending'}</td>
            </tr>
            <tr>
                <td>Curfew Validation</td>
                <td>{len(state.get('curfew_issues', []))}</td>
                <td>{'✓ Complete' if state.get('curfew_validation_complete') else '⏳ Pending'}</td>
            </tr>
            <tr>
                <td>Regulatory Validation</td>
                <td>{len(state.get('regulatory_issues', []))}</td>
                <td>{'✓ Complete' if state.get('regulatory_validation_complete') else '⏳ Pending'}</td>
            </tr>
            <tr>
                <td>Routing Validation</td>
                <td>{len(state.get('routing_issues', []))}</td>
                <td>{'✓ Complete' if state.get('routing_validation_complete') else '⏳ Pending'}</td>
            </tr>
            <tr>
                <td>Pattern Validation</td>
                <td>{len(state.get('pattern_issues', []))}</td>
                <td>{'✓ Complete' if state.get('pattern_validation_complete') else '⏳ Pending'}</td>
            </tr>
        </table>

        <p style="text-align: center; color: #666; margin-top: 40px;">
            <em>Report generated by Schedule Validation Agent</em>
        </p>
    </div>
</body>
</html>
"""

        return html

    def _generate_csv_report(self, state: Dict[str, Any]) -> str:
        """Generate CSV report"""
        issues = state.get("all_issues", [])

        csv = "Flight Number,Severity,Category,Issue Type,Description,Recommended Action,Impact\n"

        for issue in issues:
            flight_num = issue.get('flight_number', 'N/A')
            severity = issue.get('severity', 'unknown')
            category = issue.get('category', 'unknown')
            issue_type = issue.get('issue_type', 'unknown')
            description = issue.get('description', '').replace('"', '""')
            action = issue.get('recommended_action', '').replace('"', '""')
            impact = issue.get('impact', '').replace('"', '""')

            csv += f'"{flight_num}","{severity}","{category}","{issue_type}","{description}","{action}","{impact}"\n'

        return csv
