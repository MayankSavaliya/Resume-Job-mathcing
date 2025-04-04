import json
import csv
import ast
import networkx as nx
import numpy as np
import pandas as pd

# Set matplotlib backend to non-interactive Agg before importing matplotlib
import matplotlib
matplotlib.use('Agg')  # Must be before any other matplotlib imports

import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from scipy.optimize import linear_sum_assignment
import os
import base64
from io import BytesIO

class ResumeMatchingSystem:
    def __init__(self):
        self.candidates = []
        self.jobs = []
        self.skill_graph = nx.DiGraph()
        self.suitability_matrix = None
        self.min_score_threshold = 5  # Default threshold

    def add_candidate(self, candidate_id, name, skills, experience_years=0, salary_expectation=None, application_date=None):
        """Add a candidate with skills, experience, and salary expectation."""
        candidate = {
            'id': candidate_id,
            'name': name,
            'skills': skills,  # Dictionary of skill:level (0-10)
            'experience_years': experience_years,
            'salary_expectation': salary_expectation,
            'application_date': application_date if application_date else datetime.now()
        }
        self.candidates.append(candidate)

        for skill in skills.keys():
            if not self.skill_graph.has_node(skill):
                self.skill_graph.add_node(skill)

        return candidate_id

    def save_suitability_to_csv(self, filename="suitability_scores.csv"):
        """Save the candidate-job suitability matrix as a CSV file."""
        if self.suitability_matrix is None:
            self.calculate_suitability_scores()

        candidate_labels = [f"{c['name']} ({c['id']})" for c in self.candidates]
        job_labels = [f"{j['title']} ({j['id']})" for j in self.jobs]

        # Convert matrix to DataFrame
        df = pd.DataFrame(self.suitability_matrix, index=candidate_labels, columns=job_labels)

        # Save to CSV
        df.to_csv(filename, index=True)
        print(f"Suitability scores saved to {filename}")

    def add_job(self, job_id, title, required_skills, importance_weights=None, salary_range=None):
        """Add a job with required skills, weights, and salary range."""
        if importance_weights is None:
            importance_weights = {skill: 1 for skill in required_skills}

        job = {
            'id': job_id,
            'title': title,
            'required_skills': required_skills,
            'importance_weights': importance_weights,
            'salary_range': salary_range
        }
        self.jobs.append(job)

        for skill in required_skills:
            if not self.skill_graph.has_node(skill):
                self.skill_graph.add_node(skill)

        return job_id

    def add_skill_relationship(self, skill1, skill2, weight=1.0):
        """Add an edge between two skills in the skill graph with a weight."""
        if not self.skill_graph.has_node(skill1):
            self.skill_graph.add_node(skill1)
        if not self.skill_graph.has_node(skill2):
            self.skill_graph.add_node(skill2)
        self.skill_graph.add_edge(skill1, skill2, weight=weight)

    def calculate_suitability_scores(self):
        """Calculate scores using skills, experience, salary, and skill relationships."""
        if not self.candidates or not self.jobs:
            raise ValueError("Need at least one candidate and job to calculate scores!")

        n_candidates = len(self.candidates)
        n_jobs = len(self.jobs)
        self.suitability_matrix = np.zeros((n_candidates, n_jobs))

        for i, candidate in enumerate(self.candidates):
            for j, job in enumerate(self.jobs):
                skill_score = 0
                for skill, weight in job['importance_weights'].items():
                    if skill in candidate['skills']:
                        skill_score += candidate['skills'][skill] * weight

                related_bonus = 0
                for job_skill in job['required_skills']:
                    if job_skill not in candidate['skills']:
                        for cand_skill in candidate['skills']:
                            if (self.skill_graph.has_node(job_skill) and
                                self.skill_graph.has_node(cand_skill) and
                                nx.has_path(self.skill_graph, cand_skill, job_skill)):
                                path_length = nx.shortest_path_length(self.skill_graph, cand_skill, job_skill, weight='weight')
                                bonus = candidate['skills'][cand_skill] * (1 / (1 + path_length)) * 0.5
                                related_bonus += bonus

                exp_bonus = min(candidate['experience_years'], 5)

                salary_penalty = 0
                if candidate['salary_expectation'] and job['salary_range']:
                    min_salary, max_salary = job['salary_range']
                    if candidate['salary_expectation'] > max_salary:
                        salary_penalty = min(5, (candidate['salary_expectation'] - max_salary) // 10000)

                # Calculate total score and cap it at 100
                total_score = skill_score + related_bonus + exp_bonus - salary_penalty
                self.suitability_matrix[i, j] = min(100, max(0, total_score))  # Cap score between 0-100

        return self.suitability_matrix

    def set_min_score(self, threshold):
        self.min_score_threshold = threshold

    def find_optimal_matches(self):
        if self.suitability_matrix is None:
            self.calculate_suitability_scores()

        cost_matrix = -self.suitability_matrix.copy()
        filtered_cost_matrix = cost_matrix.copy()
        filtered_cost_matrix[self.suitability_matrix < self.min_score_threshold] = np.inf

        try:
            candidate_indices, job_indices = linear_sum_assignment(filtered_cost_matrix)
            
            matches = []
            for cand_idx, job_idx in zip(candidate_indices, job_indices):
                score = self.suitability_matrix[cand_idx, job_idx]
                if score >= self.min_score_threshold:
                    matches.append({
                        'candidate': self.candidates[cand_idx],
                        'job': self.jobs[job_idx],
                        'score': score
                    })
                    
            return matches
            
        except ValueError:
            # If no feasible assignment exists (all scores below threshold)
            return []

    def generate_report(self, matches=None):
        """Generate a detailed report of the matches."""
        if matches is None:
            matches = self.find_optimal_matches()

        report_data = []
        for match in matches:
            candidate = match['candidate']
            job = match['job']
            matched_skills = set(candidate['skills'].keys()) & set(job['required_skills'])

            # Properly determine salary status
            salary_status = "N/A"
            if candidate['salary_expectation'] is not None and job['salary_range'] is not None:
                min_salary, max_salary = job['salary_range']
                exp = candidate['salary_expectation']
                
                if exp < min_salary:
                    salary_status = "Below"
                elif exp > max_salary:
                    salary_status = "Above"
                else:
                    salary_status = "Within"

            report_data.append({
                'Candidate': candidate['name'],
                'Job': job['title'],
                'Score': round(match['score'], 1),
                'Experience': candidate['experience_years'],
                'Matched Skills': ', '.join(matched_skills),
                'Salary Status': salary_status
            })

        return pd.DataFrame(report_data)

    def visualize_suitability(self, return_base64=False, show_annotations=True):
        """Visualize the suitability matrix as a heatmap with improved readability for large matrices."""
        if self.suitability_matrix is None:
            self.calculate_suitability_scores()
            
        # Determine if matrix is too large for annotations
        n_candidates = len(self.candidates)
        n_jobs = len(self.jobs)
        is_large_matrix = (n_candidates > 10 or n_jobs > 10)
        
        # Set larger figure size for big matrices
        figsize = (10, 7) if not is_large_matrix else (12, 8)
        plt.figure(figsize=figsize)
        
        candidate_labels = [f"{c['name']} ({c['id']})" for c in self.candidates]
        job_labels = [f"{j['title']} ({j['id']})" for j in self.jobs]

        # Use a custom colormap to represent scores from 0-100
        # Adjust annotation settings based on matrix size
        if is_large_matrix and not show_annotations:
            # For large matrices, don't show annotations by default
            sns.heatmap(self.suitability_matrix, 
                        xticklabels=job_labels, yticklabels=candidate_labels,
                        cmap="YlGnBu", cbar=True, vmin=0, vmax=100)
        else:
            # For smaller matrices or when explicitly requested, show annotations
            sns.heatmap(self.suitability_matrix, annot=True, fmt=".1f",
                        xticklabels=job_labels, yticklabels=candidate_labels,
                        cmap="YlGnBu", cbar=True, vmin=0, vmax=100)

        plt.title("Candidate-Job Suitability Scores (0-100)")
        plt.xlabel("Jobs")
        plt.ylabel("Candidates")
        
        # For large matrices, rotate the x-axis labels for better readability
        if is_large_matrix:
            plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        
        if return_base64:
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=120)  # Higher DPI for better quality
            buf.seek(0)
            plt.close()
            return base64.b64encode(buf.getvalue()).decode('utf-8')
        else:
            plt.show(block=False)
            plt.pause(2)
            plt.close()
            
    def get_suitability_as_html(self):
        """Return the suitability matrix as an HTML table."""
        if self.suitability_matrix is None:
            self.calculate_suitability_scores()
        
        candidate_labels = [f"{c['name']} ({c['id']})" for c in self.candidates]
        job_labels = [f"{j['title']} ({j['id']})" for j in self.jobs]
        
        # Convert to pandas DataFrame for easy HTML conversion
        df = pd.DataFrame(self.suitability_matrix, 
                         index=candidate_labels, 
                         columns=job_labels)
        
        # Format numbers to 1 decimal place
        df = df.round(1)
        
        # Add styling to highlight high and low values
        def style_cells(val):
            color = ''
            if val >= 80:
                color = 'background-color: #28a745; color: white'
            elif val >= 60:
                color = 'background-color: #5cb85c; color: white'
            elif val >= 40:
                color = 'background-color: #5bc0de; color: white'
            elif val >= 20:
                color = 'background-color: #d9edf7'
            return color
        
        styled_df = df.style.applymap(style_cells)
        return styled_df.to_html()

    def visualize_skill_graph(self, return_base64=False):
        """Visualize the skill relationship graph."""
        plt.figure(figsize=(8, 6))
        pos = nx.spring_layout(self.skill_graph, seed=42)
        nx.draw(self.skill_graph, pos, with_labels=True, node_color='lightblue',
                node_size=500, font_size=10, edge_color='gray')
        edge_labels = nx.get_edge_attributes(self.skill_graph, 'weight')
        nx.draw_networkx_edge_labels(self.skill_graph, pos, edge_labels=edge_labels)
        plt.title("Skill Relationship Graph")
        plt.axis('off')
        
        if return_base64:
            buf = BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close()
            return base64.b64encode(buf.getvalue()).decode('utf-8')
        else:
            plt.show(block=False)
            plt.pause(2)
            plt.close()

    def load_skill_relationships_from_csv(self, filename):
        """Load skill relationships from CSV."""
        try:
            with open(filename, mode='r', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    if len(row) == 3:
                        skill1, skill2, weight = row
                        self.add_skill_relationship(skill1.strip(), skill2.strip(), float(weight))
        except Exception as e:
            print(f"Error loading skill relationships: {e}")

    def load_candidates_from_csv(self, filename):
        """Load candidates from CSV with improved error handling."""
        try:
            with open(filename, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    try:
                        # Handle skills - could be stored in different formats
                        if 'skills' in row:
                            try:
                                # Try parsing as JSON
                                skills = json.loads(row['skills'].replace("'", "\""))
                            except json.JSONDecodeError:
                                # If that fails, try evaluating as Python dict
                                try:
                                    skills = ast.literal_eval(row['skills'])
                                except (ValueError, SyntaxError):
                                    print(f"Skipping candidate {row.get('name', 'unknown')} due to invalid skills format.")
                                    continue
                        else:
                            skills = {}
                        
                        # Parse other fields with error handling
                        try:
                            candidate_id = int(row.get('id', 0))
                        except (ValueError, TypeError):
                            print(f"Invalid ID for candidate {row.get('name', 'unknown')}")
                            continue
                            
                        name = row.get('name', '').strip()
                        if not name:
                            print("Skipping candidate with no name")
                            continue
                        
                        # Handle experience years
                        try:
                            experience_years = int(row.get('experience_years', 0))
                        except (ValueError, TypeError):
                            experience_years = 0
                            print(f"Invalid experience years for {name}, defaulting to 0")
                        
                        # Handle salary expectation - might be empty
                        salary_expectation = None
                        if row.get('salary_expectation') and row['salary_expectation'].strip():
                            try:
                                salary_expectation = float(row['salary_expectation'])
                            except (ValueError, TypeError):
                                print(f"Invalid salary expectation for {name}, defaulting to None")
                        
                        # Handle application date
                        application_date = None
                        if row.get('application_date') and row['application_date'].strip():
                            try:
                                application_date = datetime.strptime(row['application_date'], '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                # Try alternative formats
                                try:
                                    application_date = datetime.strptime(row['application_date'], '%Y-%m-%d')
                                except ValueError:
                                    print(f"Invalid date format for {name}, using current date")
                        
                        # Add the candidate
                        self.add_candidate(candidate_id, name, skills, experience_years, salary_expectation, application_date)
                        print(f"Successfully loaded candidate: {name}")
                        
                    except Exception as e:
                        print(f"Error processing candidate: {e}")
                        
        except Exception as e:
            print(f"Error loading candidates: {e}")

    def load_jobs_from_csv(self, filename):
        """Load jobs from CSV with improved error handling."""
        try:
            with open(filename, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                rows = list(reader)  # Convert iterator to list

                for row in rows:
                    try:
                        # Fix JSON parsing issues
                        required_skills = json.loads(row['required_skills'].replace("'", "\""))
                        importance_weights = json.loads(row['importance_weights'].replace("'", "\""))

                        # Handle tuple salary range correctly
                        salary_range = ast.literal_eval(row['salary_range'])

                        self.add_job(
                            int(row['id']), row['title'].strip(), required_skills,
                            importance_weights, salary_range
                        )
                        print(f"Successfully loaded job: {row['title']}")
                    except Exception as e:
                        print(f"Error loading job {row.get('title', 'unknown')}: {e}")
        except Exception as e:
            print(f"Error loading jobs: {e}")

    def get_all_skills(self):
        """Return a list of all skills in the system."""
        return list(self.skill_graph.nodes())
