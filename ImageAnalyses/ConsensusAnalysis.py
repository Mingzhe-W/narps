#!/usr/bin/env python
# coding: utf-8
"""
run consensus analysis to identify overall pattern
analysis method developed by T Nichols and J Mumford
"""


import os
import sys
import argparse
import glob
import numpy
import nibabel
import nilearn.plotting
import nilearn.input_data
import matplotlib.pyplot as plt
from statsmodels.stats.multitest import multipletests
from narps import Narps, hypnums, hypotheses
from narps import NarpsDirs # noqa, flake8 issue
from utils import log_to_file, t_corr


def run_ttests(narps, logfile,
               overwrite=True):
    masker = nilearn.input_data.NiftiMasker(
        mask_img=narps.dirs.MNI_mask)
    results_dir = narps.dirs.dirs['consensus']

    func_name = sys._getframe().f_code.co_name
    log_to_file(
        logfile, '%s' %
        func_name)

    if not os.path.exists(results_dir):
        os.mkdir(results_dir)

    for hyp in hypnums:
        if not overwrite and os.path.exists(os.path.join(
                results_dir,
                'hypo%d_1-fdr.nii.gz' % hyp)):
            print('using existing results')
            continue
        print('running consensus analysis for hypothesis', hyp)
        maps = glob.glob(os.path.join(
            narps.dirs.dirs['output'],
            'zstat/*/hypo%d_unthresh.nii.gz' % hyp))
        maps.sort()
        data = masker.fit_transform(maps)

        # get estimated mean, variance, and correlation for t_corr
        img_mean = numpy.mean(data)
        img_var = numpy.mean(numpy.var(data, 1))
        cc = numpy.corrcoef(data)
        log_to_file(
            logfile,
            'mean = %f, var = %f, mean_cc = %f' %
            (img_mean, img_var,
             numpy.mean(cc[numpy.triu_indices_from(cc, 1)])))

        # perform t-test
        tvals, pvals = t_corr(data,
                              res_mean=img_mean,
                              res_var=img_var,
                              Q=cc)

        # move back into image format
        timg = masker.inverse_transform(tvals)
        timg.to_filename(os.path.join(results_dir, 'hypo%d_t.nii.gz' % hyp))
        pimg = masker.inverse_transform(1-pvals)
        pimg.to_filename(os.path.join(results_dir, 'hypo%d_1-p.nii.gz' % hyp))
        fdr_results = multipletests(pvals[0, :], 0.05, 'fdr_tsbh')
        log_to_file(
            logfile,
            "%d voxels significant at FDR corrected p<.05" %
            numpy.sum(fdr_results[0]))
        fdrimg = masker.inverse_transform(1 - fdr_results[1])
        fdrimg.to_filename(os.path.join(
            results_dir,
            'hypo%d_1-fdr.nii.gz' % hyp))

        # compute tau^2 per Tom's notes in CorrelatedMetaNotes.html
        def tau(data, Q):
            n = data.shape[0]
            R = numpy.eye(n) - numpy.ones((n, 1)).dot(numpy.ones((1, n)))/n
            sampvar_est = numpy.trace(R.dot(Q))
            tau2 = numpy.zeros(data.shape[1])
            for i in range(data.shape[1]):
                Y = data[:, i]
                tau2[i] = (1/sampvar_est)*Y.T.dot(R).dot(Y)
            return(numpy.sqrt(tau2))

        tau_est = tau(data, cc)
        tauimg = masker.inverse_transform(tau_est)
        tauimg.to_filename(os.path.join(
            results_dir,
            'hypo%d_tau.nii.gz' % hyp))


def mk_figures(narps, logfile, thresh=0.95):

    func_name = sys._getframe().f_code.co_name
    log_to_file(
        logfile, '%s' %
        func_name)
    masker = nilearn.input_data.NiftiMasker(
        mask_img=narps.dirs.MNI_mask)

    fig, ax = plt.subplots(7, 1, figsize=(12, 24))
    cut_coords = [-24, -10, 4, 18, 32, 52, 64]

    for i, hyp in enumerate(hypnums):
        pmap = os.path.join(
            narps.dirs.dirs['consensus'],
            'hypo%d_1-fdr.nii.gz' % hyp)
        tmap = os.path.join(
            narps.dirs.dirs['consensus'],
            'hypo%d_t.nii.gz' % hyp)
        pimg = nibabel.load(pmap)
        timg = nibabel.load(tmap)
        pdata = pimg.get_fdata()
        tdata = timg.get_fdata()[:, :, :, 0]
        threshdata = (pdata > thresh)*tdata
        threshimg = nibabel.Nifti1Image(threshdata, affine=timg.affine)
        nilearn.plotting.plot_stat_map(
            threshimg,
            threshold=0.1,
            display_mode="z",
            colorbar=True,
            title='hyp %d:' % hyp+hypotheses[hyp],
            vmax=8,
            cmap='jet',
            cut_coords=cut_coords,
            axes=ax[i])

    plt.savefig(os.path.join(
        narps.dirs.dirs['figures'],
        'consensus_map.pdf'), bbox_inches='tight')
    plt.close(fig)

    # create tau figures
    fig, ax = plt.subplots(7, 1, figsize=(12, 24))
    tauhist = {}
    for i, hyp in enumerate(hypnums):
        taumap = os.path.join(
            narps.dirs.dirs['consensus'],
            'hypo%d_tau.nii.gz' % hyp)
        tauimg = nibabel.load(taumap)
        taudata = masker.fit_transform(tauimg)
        log_to_file(
            logfile, 'hyp %d: median tau %0.3f, max tau %0.3f' %
            (hyp, numpy.median(taudata), numpy.max(taudata)))

        tauhist[i] = numpy.histogram(
            taudata, bins=numpy.arange(0, 5, 0.01))
        nilearn.plotting.plot_stat_map(
            tauimg,
            threshold=0.0,
            display_mode="z",
            colorbar=True,
            title='hyp %d:' % hyp+hypotheses[hyp],
            vmax=4.,
            cmap='jet',
            cut_coords=cut_coords,
            axes=ax[i])
    plt.savefig(os.path.join(
        narps.dirs.dirs['figures'],
        'tau_maps.pdf'), bbox_inches='tight')
    plt.close(fig)

    # create tau histograms
    fig, ax = plt.subplots(7, 1, figsize=(12, 24))
    for i, hyp in enumerate(hypnums):
        ax[i].plot(tauhist[i][1][1:], tauhist[i][0])
        ax[i].set_xlabel('tau')
        ax[i].set_ylabel('# of voxels')
        ax[i].set_title('hyp %d:' % hyp+hypotheses[hyp])
        plt.tight_layout()
    plt.savefig(os.path.join(
        narps.dirs.dirs['figures'],
        'tau_histograms.pdf'), bbox_inches='tight')
    plt.close(fig)


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(
        description='Analyze NARPS data')
    parser.add_argument('-b', '--basedir',
                        help='base directory')
    parser.add_argument('-d', '--detailed',
                        action='store_true',
                        help='generate detailed team-level figures')
    parser.add_argument('-t', '--test',
                        action='store_true',
                        help='use testing mode (no processing)')
    args = parser.parse_args()

    # set up base directory
    if args.basedir is not None:
        basedir = args.basedir
    elif 'NARPS_BASEDIR' in os.environ:
        basedir = os.environ['NARPS_BASEDIR']
        print("using basedir specified in NARPS_BASEDIR")
    else:
        basedir = '/data'
        print("using default basedir:", basedir)

    # setup main class
    narps = Narps(basedir)
    narps.load_data()
    narps.dirs.dirs['consensus'] = os.path.join(
        narps.dirs.dirs['output'],
        'consensus_analysis')
    if not os.path.exists(narps.dirs.dirs['consensus']):
        os.mkdir(narps.dirs.dirs['consensus'])
    narps.write_data()

    logfile = os.path.join(
        narps.dirs.dirs['logs'],
        'ConsensusAnalysis.txt')
    if not args.test:
        log_to_file(
            logfile, 'running ConsensusAnalysis',
            flush=True)

        run_ttests(narps, logfile)
        mk_figures(narps, logfile)
