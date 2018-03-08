#This script allows to detect LexA orthologous from a specified taxonomic group, retrieve the flanking regions
#and find motifs

import json, os, sys
from Bio.Blast import NCBIWWW, NCBIXML
from Bio import Entrez, SeqIO, pairwise2
from Bio.SubsMat.MatrixInfo import blosum62

Entrez.email = "antoniocolladopadilla12@gmail.com"

#Capture input file (JSON format) from command line

input_file = sys.argv[1]


#Create dictionary with input data

def createinput(filename):
    dict = {}
    with open(filename) as f:
        for k, v in json.load(f).items():
            dict[k] = v
    print "Creating input dictionary."
    return dict


input = createinput(input_file)



# Blast search


def blastsearch():

    resultslist = []

    print "Performing Blast search"

    ids = open(input["protein_ids"]).read()             #Open fasta file

    handleresults = NCBIWWW.qblast(program='blastp', database='refseq_protein', sequence=ids,        #BLAST search
                                   entrez_query=input["restriction_taxon"],
                                   expect=input["e_value_threshold"], hitlist_size=10)

    blast_records = NCBIXML.parse(handleresults)        #Parse BLAST results

    blast_records = list(blast_records)

    count = input["e_value_threshold"]

    #Create a list with all the hits

    all_hits = []

    for query_search in blast_records:

        for i in query_search.descriptions:

            if i.accession not in all_hits:
                all_hits.append(i.accession)


    # Create matrix: rows = queries, columns = blast_hit_IDS

    matrix = [[] for i in range(len(blast_records))]

    for i in range(len(blast_records)):

        results, evals = [], []

        for result in blast_records[i].descriptions:

            results.append(result.accession)
            evals.append(result.e)

        for hit in all_hits:

            if hit in results:
                matrix[i].append(evals[results.index(hit)])         #Add to the list of the current query its E-values, following the order of the results list

            else:
                matrix[i].append(100)             #If that query does not have the current hit as a result, no E-value but 100 is added


    #Test

    test_file = 'blast_results.txt'

    test_file = open(test_file, 'w')

    for hit in all_hits:
        test_file.write(hit + '\t')

    return all_hits, matrix



# Entrez search

def entrezsearch():

    acc_list, position_list, strand_list, flanking_regions = [], [], [], []

    results, matrix = blastsearch()

    print "Retrieving Entrez queries."

    for acc in results:

        handle = Entrez.efetch(db="protein", id=acc, rettype='ipg',
                               retmode='xml')

        #Parse results

        records = Entrez.read(handle)

        print acc

        #Get the strand and positions of the gene, and the accession-version id of the genome
        #Only one result per BLAST match

        for record in records[0]['ProteinList']:

            if record.attributes['source'] == "RefSeq":

                try:

                    acc_list.append(record['CDSList'][0].attributes['accver'])

                    if record['CDSList'][0].attributes['strand'] == '+':

                        position_list.append(record['CDSList'][0].attributes['start'])
                        strand_list.append(1)

                    else:

                        position_list.append(record['CDSList'][0].attributes['stop'])
                        strand_list.append(2)

                except KeyError:

                    pass

    print "Retrieving flanking sequences."

    #Use the collected data to retrieve the genomic regions

    for i in range(len(acc_list)):

        if strand_list[i] == 1:
            flanking_handle = Entrez.efetch(db="nucleotide", id=acc_list[i], rettype="fasta", strand=strand_list[i],
                                            seq_start=int(position_list[i]) - int(input["upstream_region"]),
                                            seq_stop=int(position_list[i]) + int(input["downstream_region"]))

        else:
            flanking_handle = Entrez.efetch(db="nucleotide", id=acc_list[i], rettype="fasta", strand=strand_list[i],
                                            seq_start=int(position_list[i]) - int(input["downstream_region"]),
                                            seq_stop=int(position_list[i]) + int(input["upstream_region"]))

        flanking_parse = SeqIO.read(flanking_handle, "fasta")
        flanking_regions.append(flanking_parse.seq._data)

    return flanking_regions, acc_list



#Remove similar sequences

def nucleotide_identity():

    flanking_regions, acc_list = entrezsearch()

    removed_regions, removed_acc = [], []

    print "Removing similar sequences."

    length = len(flanking_regions)

    for i in range(length):

        for k in range(i + 1, length):

            #Perform pairwise alignment

            alignment = pairwise2.align.globalds(flanking_regions[i], flanking_regions[k], blosum62, -10, -1)
            seq1, seq2 = alignment[0][0], alignment[0][1]
            matches = ""

            #Count matches

            for base1, base2 in zip(seq1, seq2):
                if base1 == base2 and base1 != '-':
                    matches += base1

            #Compute identity and remove from the list if greater than the threshold

            identity = float(len(matches)) / len(seq1) * 100

            if identity > input["identity_threshold"]:
                removed_regions.append(flanking_regions[i])
                removed_acc.append(acc_list[i])
                break

    #Write filtered results in fasta file

    output_fasta = 'filtered_flanking_regions.fasta'

    output_write = open(output_fasta, 'w')

    for i in range(len(flanking_regions)):
        if flanking_regions[i] not in removed_regions and acc_list[i] not in removed_acc:
            output_write.write('>' + acc_list[i] + "\n" + flanking_regions[i] + "\n")

    output_write.close()

    return output_fasta


#Motif search function

def motif_search():

    #Input will be the fasta file created in nucleotide_identity

    output_fasta = nucleotide_identity()

    cmd = "meme {input} -o {out} -dna -w {width} -mod {mode}".format(input=output_fasta, out=input["restriction_taxon"],
                                                                     width=input["motif_width"],
                                                                     mode=input["motif_distribution"])

    print "Performing motif search."

    os.system(cmd)


#Apply final function

motif_search()



